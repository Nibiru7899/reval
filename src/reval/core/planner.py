"""Revalidation planner (docs/04-algorithms.md A7, docs/10-interfaces.md §4.6, decision D7). Pure.

``build_problem`` turns the claims that need restoration into obligations and candidate runs; ``plan`` picks
the runs (CP-SAT ILP, greedy baseline, or "run everything"). The solver runs single-threaded with a fixed
seed, so the same problem always yields the same plan.
"""

import itertools
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ortools.sat.python import cp_model

from reval.core.canonical import content_id
from reval.core.status import FRESH_CLASSES, AssessInput
from reval.core.verdicts import verdict
from reval.domain.assessment import Assessment
from reval.domain.evidence import Evidence, ProducerKind
from reval.domain.plan import CandidateRun, Obligation, PlannedRun, PlanningProblem, RevalidationPlan
from reval.domain.policies import EvidenceRequirement
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass, ReasonCode, Status, Verdict

CRITICALITY_WEIGHT: dict[str, int] = {"low": 1, "medium": 3, "high": 10}

PLANNED_STATUSES: frozenset[Status] = frozenset({Status.STALE, Status.INCONCLUSIVE})
RERUN_PREFIX = "rerun:"
EXISTING_PREFIX = "existing:"

PlannerName = Literal["ilp", "greedy", "all"]
Objective = Literal["min_cost", "max_restored"]


def is_rerun_obligation(key: str) -> bool:
    """True for the mandatory ``rerun:<producer>@<subject>`` obligations of lost-fail claims."""
    return key.startswith(RERUN_PREFIX)


def rerun_key(producer_id: str, subject_id: str) -> str:
    return f"{RERUN_PREFIX}{producer_id}@{subject_id}"


def _cost_int(cost: float) -> int:
    return round(cost * 100)


# ---------------------------------------------------------------------------------------------------------
# Problem construction (P4-05)
# ---------------------------------------------------------------------------------------------------------


def _lost_fail_ids(a: Assessment) -> tuple[str, ...]:
    """Evidence ids behind a lost-fail STALE (docs/03 §3 rule 2; superseded items are already excluded)."""
    if a.status is not Status.STALE:
        return ()
    ids: set[str] = set()
    for r in a.reasons:
        if r.code is ReasonCode.EVIDENCE_INVALIDATED and r.detail.get("lost_fail") is True:
            ids.update(r.evidence_ids)
    return tuple(sorted(ids))


def _matches(e_kind: ProducerKind, fidelity: int, req: EvidenceRequirement) -> bool:
    return e_kind is req.kind and fidelity >= req.min_fidelity


def build_problem(
    snapshot: Snapshot,
    assessments: Mapping[str, Assessment],
    items: Sequence[AssessInput],
    *,
    available: Callable[[str, str], bool],
    known_out_of_domain: frozenset[tuple[str, str]] = frozenset(),
) -> PlanningProblem:
    """Obligations and candidates for every STALE or INCONCLUSIVE claim (docs/10 §4.6).

    Every conjunct of every clause becomes an obligation (nothing is dropped, D7). Lost-fail claims also get a
    mandatory ``rerun:<producer>@<subject>`` obligation in every clause, so cost-0 reuse never restores them.
    """
    by_id: dict[str, AssessInput] = {}
    for inp in items:
        by_id.setdefault(inp.evidence.id, inp)
    # Only FRESH_EXACT blocks a rerun: a deterministic producer would reproduce it (D7, round 2).
    fresh_exact = {
        (inp.evidence.producer_id, inp.evidence.subject_id)
        for inp in by_id.values()
        if inp.freshness is FreshnessClass.FRESH_EXACT
    }

    planned = [cid for cid in sorted(assessments) if assessments[cid].status in PLANNED_STATUSES]
    weights: dict[str, int] = {}
    clauses: dict[str, tuple[tuple[str, ...], ...]] = {}
    obligations: dict[str, Obligation] = {}
    regular_by_claim: dict[str, list[Obligation]] = {}

    for cid in planned:
        if cid not in snapshot.claims:
            raise ValueError(f"assessment for unknown claim {cid}")
        claim = snapshot.claims[cid]
        req = snapshot.requirements[claim.requirement_id]
        policy = snapshot.policy_for(cid)
        weights[cid] = CRITICALITY_WEIGHT[req.criticality.value]

        reruns: set[str] = set()
        for eid in _lost_fail_ids(assessments[cid]):
            if eid not in by_id:
                raise ValueError(f"lost-fail evidence {eid} of claim {cid} is not among the items")
            e = by_id[eid].evidence
            key = rerun_key(e.producer_id, e.subject_id)
            reruns.add(key)
            # A rerun obligation is shared by every claim that lost a FAIL from the same producer and subject;
            # its Obligation record names the first such claim and uses clause/conjunct index -1.
            obligations.setdefault(
                key,
                Obligation(
                    claim_id=cid,
                    clause_index=-1,
                    conjunct_index=-1,
                    requirement=EvidenceRequirement(kind=e.producer_kind),
                ),
            )

        regular: list[Obligation] = []
        per_clause: list[tuple[str, ...]] = []
        for k, clause in enumerate(policy.alternatives):
            keys: list[str] = []
            for i, r in enumerate(clause):
                o = Obligation(claim_id=cid, clause_index=k, conjunct_index=i, requirement=r)
                obligations[o.key] = o
                regular.append(o)
                keys.append(o.key)
            per_clause.append((*keys, *sorted(reruns)))
        clauses[cid] = tuple(per_clause)
        regular_by_claim[cid] = regular

    kinds: dict[str, ProducerKind] = {}
    predictors: dict[str, tuple[str, ...]] = {}
    satisfies: dict[str, set[str]] = {}
    meta: dict[str, tuple[str, str, float, str | None]] = {}  # id -> (producer, subject, cost, evidence id)

    # Reuse candidates: fresh PASS items, decided inside the same matching as new runs (D7).
    for cid in planned:
        claim = snapshot.claims[cid]
        req = snapshot.requirements[claim.requirement_id]
        for eid in sorted(by_id):
            inp = by_id[eid]
            ev: Evidence = inp.evidence
            if (
                inp.freshness not in FRESH_CLASSES
                or ev.producer_kind is ProducerKind.WAIVER
                or ev.subject_id != claim.subject_id
                or ev.result.quantity != req.quantity
                or ev.producer_id not in snapshot.producers  # unknown predictors: never usable (fail closed)
                or verdict(ev, req)[0] is not Verdict.PASS
            ):
                continue
            reuse_hits = [
                o.key
                for o in regular_by_claim[cid]
                if _matches(ev.producer_kind, ev.fidelity, o.requirement)
                and (not o.requirement.in_domain or ev.result.in_domain is True)
            ]
            if not reuse_hits:
                continue
            jid = f"{EXISTING_PREFIX}{ev.id}"
            kinds[jid] = ev.producer_kind
            predictors[jid] = tuple(sorted(snapshot.producers[ev.producer_id].predictors))
            meta[jid] = (ev.producer_id, ev.subject_id, 0.0, ev.id)
            satisfies.setdefault(jid, set()).update(reuse_hits)

    # New-run candidates.
    subjects = sorted({snapshot.claims[cid].subject_id for cid in planned})
    for pid in sorted(snapshot.producers):
        p = snapshot.producers[pid]
        if p.kind is ProducerKind.WAIVER:
            continue
        for sid in subjects:
            if (pid, sid) in fresh_exact or not available(pid, sid):
                continue
            if p.kind is ProducerKind.ML_PREDICTION and (pid, sid) in known_out_of_domain:
                continue  # regardless of the conjunct's in_domain flag
            hits = {
                o.key
                for cid in planned
                if snapshot.claims[cid].subject_id == sid
                and snapshot.requirements[snapshot.claims[cid].requirement_id].quantity in p.quantities
                for o in regular_by_claim[cid]
                if _matches(p.kind, p.fidelity, o.requirement)
            }
            rk = rerun_key(pid, sid)
            if rk in obligations:
                hits.add(rk)
            if not hits:
                continue
            jid = f"{pid}@{sid}"
            kinds[jid] = p.kind
            predictors[jid] = tuple(sorted(p.predictors))
            meta[jid] = (pid, sid, p.cost, None)
            satisfies[jid] = hits

    sat_of: dict[str, list[str]] = {}
    for jid in sorted(satisfies):
        for okey in satisfies[jid]:
            sat_of.setdefault(okey, []).append(jid)

    incompatible: set[tuple[str, str, str, str]] = set()
    for cid in planned:
        for k in range(len(clauses[cid])):
            regs = [o for o in regular_by_claim[cid] if o.clause_index == k]
            for o, o2 in itertools.permutations(regs, 2):
                if o2.requirement.kind not in o.requirement.independent_of:
                    continue
                for j in sat_of.get(o.key, []):
                    for j2 in sat_of.get(o2.key, []):
                        if j == j2:
                            continue  # distinctness already forbids it
                        if kinds[j] is kinds[j2] or set(predictors[j]) & set(predictors[j2]):
                            incompatible.add((j, o.key, j2, o2.key))

    candidates = tuple(
        CandidateRun(
            id=jid,
            producer_id=meta[jid][0],
            subject_id=meta[jid][1],
            cost=meta[jid][2],
            satisfies=tuple(sorted(satisfies[jid])),
            predictors=predictors[jid],
            existing_evidence_id=meta[jid][3],
        )
        for jid in sorted(satisfies)
    )
    return PlanningProblem(
        snapshot_id=snapshot.id,
        claim_weights=weights,
        clauses=clauses,
        obligations={key: obligations[key] for key in sorted(obligations)},
        candidates=candidates,
        incompatible=tuple(sorted(incompatible)),
    )


# ---------------------------------------------------------------------------------------------------------
# Shared clause matching
# ---------------------------------------------------------------------------------------------------------

Assignment = tuple[tuple[str, str], ...]  # ((obligation key, candidate id), ...) in clause order


@dataclass(frozen=True)
class _Index:
    problem: PlanningProblem
    cand: dict[str, CandidateRun]
    sat: dict[str, tuple[str, ...]]  # obligation key -> candidate ids, sorted
    incompatible: frozenset[tuple[str, str, str, str]]  # both orientations

    @staticmethod
    def of(problem: PlanningProblem) -> "_Index":
        cand = {c.id: c for c in problem.candidates}
        if len(cand) != len(problem.candidates):
            raise ValueError("duplicate candidate ids")
        sat: dict[str, list[str]] = {o: [] for o in problem.obligations}
        for c in problem.candidates:
            if c.cost < 0:
                raise ValueError(f"candidate {c.id} has a negative cost")
            for o in c.satisfies:
                if o not in sat:
                    raise ValueError(f"candidate {c.id} satisfies unknown obligation {o}")
                sat[o].append(c.id)
        for cid, cls in problem.clauses.items():
            if cid not in problem.claim_weights:
                raise ValueError(f"claim {cid} has clauses but no weight")
            for clause in cls:
                for o in clause:
                    if o not in sat:
                        raise ValueError(f"clause of {cid} references unknown obligation {o}")
        inc: set[tuple[str, str, str, str]] = set()
        for j, o, j2, o2 in problem.incompatible:
            inc.add((j, o, j2, o2))
            inc.add((j2, o2, j, o))
        return _Index(problem, cand, {o: tuple(sorted(v)) for o, v in sat.items()}, frozenset(inc))

    def assignments(
        self, claim_id: str, k: int, allowed: frozenset[str] | None = None
    ) -> Iterator[Assignment]:
        """Valid full assignments of clause ``k`` in lexicographic order (distinct runs, independence)."""
        clause = self.problem.clauses.get(claim_id, ())[k]
        lists = [[j for j in self.sat[o] if allowed is None or j in allowed] for o in clause]
        chosen: list[tuple[str, str]] = []

        def rec(i: int) -> Iterator[Assignment]:
            if i == len(clause):
                yield tuple(chosen)
                return
            o = clause[i]
            for j in lists[i]:
                if not is_rerun_obligation(o) and any(
                    j == j2 for o2, j2 in chosen if not is_rerun_obligation(o2)
                ):
                    continue  # one run counts once per clause
                if any((j, o, j2, o2) in self.incompatible for o2, j2 in chosen):
                    continue
                chosen.append((o, j))
                yield from rec(i + 1)
                chosen.pop()

        return rec(0)

    def first(self, claim_id: str, k: int, allowed: frozenset[str] | None = None) -> Assignment | None:
        return next(self.assignments(claim_id, k, allowed), None)

    def covered_clause(self, claim_id: str, allowed: frozenset[str]) -> int | None:
        for k in range(len(self.problem.clauses.get(claim_id, ()))):
            if self.first(claim_id, k, allowed) is not None:
                return k
        return None

    def restorable(self) -> dict[str, bool]:
        """A claim is restorable iff some clause can be covered with every candidate selected."""
        return {
            cid: any(self.first(cid, k) is not None for k in range(len(self.problem.clauses.get(cid, ()))))
            for cid in sorted(self.problem.claim_weights)
        }


def _finish(
    idx: _Index,
    selected: frozenset[str],
    chosen: Mapping[str, int],
    *,
    planner: PlannerName,
    objective: Objective,
    budget: float | None,
    solver_status: str,
    reproducible: bool,
    keep_idle_runs: bool,
) -> RevalidationPlan:
    restorable = idx.restorable()
    discharges: dict[str, set[str]] = {}
    chosen_clauses: dict[str, int] = {}
    for cid in sorted(chosen):
        k = chosen[cid]
        a = idx.first(cid, k, selected)
        if a is None:
            raise RuntimeError(f"internal error: clause {k} of {cid} is not covered by the selected runs")
        chosen_clauses[cid] = k
        for o, j in a:
            discharges.setdefault(j, set()).add(o)
    runs = sorted(
        (
            PlannedRun(
                candidate_id=c.id,
                producer_id=c.producer_id,
                subject_id=c.subject_id,
                cost=c.cost,
                discharges=tuple(sorted(discharges.get(c.id, ()))),
            )
            for c in idx.problem.candidates
            if c.id in selected
            and c.existing_evidence_id is None
            and (keep_idle_runs or c.id in discharges or c.cost > 0)
        ),
        key=lambda r: (r.cost, r.candidate_id),
    )
    total = 0.0
    for r in runs:
        total += r.cost
    draft = RevalidationPlan(
        id="",
        snapshot_id=idx.problem.snapshot_id,
        planner=planner,
        objective=objective,
        budget=budget,
        runs=tuple(runs),
        total_cost=total,
        chosen_clauses=chosen_clauses,
        unrestorable=tuple(c for c, ok in restorable.items() if not ok),
        deferred=tuple(c for c, ok in restorable.items() if ok and c not in chosen_clauses),
        solver_status=solver_status,
        reproducible=reproducible,
    )
    return draft.model_copy(update={"id": content_id(draft)})


# ---------------------------------------------------------------------------------------------------------
# ILP (P4-06, P4-07)
# ---------------------------------------------------------------------------------------------------------


def _solve_ilp(
    idx: _Index, budget_int: int | None, max_time_s: float
) -> tuple[frozenset[str], dict[str, int], str]:
    p = idx.problem
    m = cp_model.CpModel()
    z = {c.id: m.new_bool_var(f"z[{c.id}]") for c in p.candidates}
    x = {(c.id, o): m.new_bool_var(f"x[{c.id},{o}]") for c in p.candidates for o in c.satisfies}
    for (j, _o), var in x.items():
        m.add(var <= z[j])
    y: dict[tuple[str, int], Any] = {}
    u = {cid: m.new_bool_var(f"u[{cid}]") for cid in sorted(p.claim_weights)}
    for cid in sorted(p.claim_weights):
        cls = p.clauses.get(cid, ())
        for k, clause in enumerate(cls):
            yk = m.new_bool_var(f"y[{cid},{k}]")
            y[(cid, k)] = yk
            for o in clause:
                terms = [x[(j, o)] for j in idx.sat[o]]
                if terms:
                    m.add(yk <= sum(terms))
                else:
                    m.add(yk == 0)
            regular = [o for o in clause if not is_rerun_obligation(o)]
            for c in p.candidates:
                own = [x[(c.id, o)] for o in regular if (c.id, o) in x]
                if len(own) > 1:
                    m.add(sum(own) <= 1)  # one run counts once per clause (distinct evidence)
        m.add(sum(y[(cid, k)] for k in range(len(cls))) + u[cid] >= 1)
    for j, o, j2, o2 in p.incompatible:
        if (j, o) in x and (j2, o2) in x:
            m.add(x[(j, o)] + x[(j2, o2)] <= 1)

    cost_terms = [_cost_int(c.cost) * z[c.id] for c in p.candidates]
    big_m = 1 + sum(_cost_int(c.cost) for c in p.candidates)
    unrestored = [p.claim_weights[cid] * u[cid] for cid in sorted(u)]
    if budget_int is not None:
        m.add(sum(cost_terms) <= budget_int)
    # min_cost and max_restored share one integer objective; with a budget it is lexicographic in effect.
    m.minimize(sum(cost_terms) + big_m * sum(unrestored))

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = max_time_s
    status = solver.solve(m)
    name = str(solver.status_name(status))
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return frozenset(), {}, name
    selected = frozenset(j for j, var in z.items() if solver.boolean_value(var))
    chosen: dict[str, int] = {}
    for cid in sorted(u):
        for k in range(len(p.clauses.get(cid, ()))):
            if solver.boolean_value(y[(cid, k)]):
                chosen[cid] = k
                break
    return selected, chosen, name


# ---------------------------------------------------------------------------------------------------------
# Greedy and "all" (P4-08)
# ---------------------------------------------------------------------------------------------------------


def _greedy(idx: _Index, budget_int: int | None) -> frozenset[str]:
    p = idx.problem
    claims = sorted(p.claim_weights)
    n_clauses = {cid: len(p.clauses.get(cid, ())) for cid in claims}
    full = {(cid, k): list(idx.assignments(cid, k)) for cid in claims for k in range(n_clauses[cid])}
    restorable = {cid for cid in claims if any(full[(cid, k)] for k in range(n_clauses[cid]))}
    cost = {c.id: c.cost for c in p.candidates}

    def progress(cid: str, k: int, sel: frozenset[str]) -> int:
        return max(sum(1 for _o, j in a if j in sel) for a in full[(cid, k)])

    def remaining(cid: str, k: int, sel: frozenset[str]) -> float:
        return min(sum(cost[j] for j in {j for _o, j in a} - sel) for a in full[(cid, k)])

    def covered(sel: frozenset[str]) -> set[str]:
        return {cid for cid in restorable if idx.covered_clause(cid, sel) is not None}

    sel: frozenset[str] = frozenset()
    spent = 0
    while True:
        open_claims = sorted(restorable - covered(sel))
        if not open_claims:
            break
        target: dict[str, tuple[int, int]] = {}  # claim -> (cheapest open clause, its progress)
        for cid in open_claims:
            ks = [k for k in range(n_clauses[cid]) if full[(cid, k)]]
            k = min(ks, key=lambda kk: (remaining(cid, kk, sel), kk))
            target[cid] = (k, progress(cid, k, sel))
        best: tuple[float, str] | None = None
        for c in p.candidates:  # sorted by id, so ties go to the smaller id
            if c.id in sel:
                continue
            if budget_int is not None and spent + _cost_int(c.cost) > budget_int:
                continue
            with_c = sel | {c.id}
            gain = sum(
                p.claim_weights[cid]
                for cid in open_claims
                if progress(cid, target[cid][0], with_c) > target[cid][1]
            )
            if gain == 0:
                continue
            ratio = gain / max(c.cost, 0.01)
            if best is None or ratio > best[0]:
                best = (ratio, c.id)
        if best is None:
            break
        sel = sel | {best[1]}
        spent += _cost_int(cost[best[1]])

    restored = covered(sel)
    for c in sorted((idx.cand[j] for j in sel), key=lambda c: (-c.cost, c.id)):
        without = sel - {c.id}
        if covered(without) >= restored:
            sel = without
    return sel


def _all(idx: _Index) -> frozenset[str]:
    return frozenset(
        c.id for c in idx.problem.candidates if c.existing_evidence_id is not None or c.satisfies
    )


# ---------------------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------------------


def plan(
    problem: PlanningProblem,
    *,
    planner: PlannerName = "ilp",
    objective: Objective = "min_cost",
    budget: float | None = None,
    max_time_s: float = 10.0,
) -> RevalidationPlan:
    """Choose the runs that restore the planned claims (docs/10 §4.6).

    ``min_cost`` restores every restorable claim at minimum cost and takes no budget. ``max_restored`` needs a
    ``budget`` and maximizes the restored criticality weight, then minimizes cost. Claims that no selection of
    candidates can restore are ``unrestorable``; restorable claims left uncovered are ``deferred``.
    """
    if objective == "max_restored":
        if budget is None:
            raise ValueError("objective 'max_restored' requires a budget")
        if budget < 0:
            raise ValueError("budget must be >= 0")
    elif objective == "min_cost":
        if budget is not None:
            raise ValueError("a budget is only valid with objective 'max_restored'")
    else:
        raise ValueError(f"unknown objective {objective!r}")
    budget_int = None if budget is None else _cost_int(budget)
    idx = _Index.of(problem)

    if planner == "ilp":
        selected, chosen, status = _solve_ilp(idx, budget_int, max_time_s)
        return _finish(
            idx,
            selected,
            chosen,
            planner=planner,
            objective=objective,
            budget=budget,
            solver_status=status,
            reproducible=status == "OPTIMAL",
            keep_idle_runs=False,
        )
    if planner == "greedy":
        selected = _greedy(idx, budget_int)
        status = "GREEDY"
    elif planner == "all":
        if objective != "min_cost":
            raise ValueError("planner 'all' ignores budgets; use objective 'min_cost'")
        selected = _all(idx)
        status = "ALL"
    else:
        raise ValueError(f"unknown planner {planner!r}")
    chosen = {
        cid: k
        for cid in sorted(problem.claim_weights)
        if (k := idx.covered_clause(cid, selected)) is not None
    }
    return _finish(
        idx,
        selected,
        chosen,
        planner=planner,
        objective=objective,
        budget=budget,
        solver_status=status,
        reproducible=True,
        keep_idle_runs=True,
    )
