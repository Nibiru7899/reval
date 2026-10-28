"""Seeded random planning problems and an independent brute-force oracle (P4-06..P4-08)."""

import itertools
import random
from dataclasses import dataclass

from reval.domain import CandidateRun, EvidenceRequirement, Obligation, PlanningProblem, ProducerKind

KINDS = [
    ProducerKind.ML_PREDICTION,
    ProducerKind.PHYSICS_SIM,
    ProducerKind.MEASUREMENT,
    ProducerKind.ANALYTIC,
]
COSTS = [0.5, 1.0, 1.25, 2.0, 3.0, 5.0, 10.0]


def random_problem(seed: int, max_candidates: int = 10, max_claims: int = 4) -> PlanningProblem:
    """A small random problem shaped like build_problem's output (kinds, independence, reruns, reuse)."""
    rng = random.Random(seed)
    n_cand = rng.randint(1, max_candidates)
    cand_kind: dict[str, ProducerKind] = {}
    cand_pred: dict[str, tuple[str, ...]] = {}
    cand_cost: dict[str, float] = {}
    cand_existing: dict[str, str | None] = {}
    for i in range(n_cand):
        existing = rng.random() < 0.2
        jid = f"existing:e{i}" if existing else f"P{i}@S"
        cand_kind[jid] = rng.choice(KINDS)
        cand_pred[jid] = tuple(sorted(rng.sample(["a", "b", "c"], rng.randint(0, 2))))
        cand_cost[jid] = 0.0 if existing else rng.choice(COSTS)
        cand_existing[jid] = f"e{i}" if existing else None
    ids = sorted(cand_kind)
    new_ids = [j for j in ids if cand_existing[j] is None]

    obligations: dict[str, Obligation] = {}
    clauses: dict[str, tuple[tuple[str, ...], ...]] = {}
    weights: dict[str, int] = {}
    sat: dict[str, set[str]] = {j: set() for j in ids}
    clause_regs: list[list[Obligation]] = []
    for c in range(rng.randint(1, max_claims)):
        cid = f"C{c}"
        weights[cid] = rng.choice([1, 3, 10])
        reruns: list[str] = []
        if new_ids and rng.random() < 0.25:
            j = rng.choice(new_ids)
            key = "rerun:" + j
            obligations.setdefault(
                key,
                Obligation(
                    claim_id=cid,
                    clause_index=-1,
                    conjunct_index=-1,
                    requirement=EvidenceRequirement(kind=cand_kind[j]),
                ),
            )
            sat[j].add(key)
            reruns.append(key)
        elif rng.random() < 0.1:
            # A lost-fail claim whose rerun candidate is unavailable: unrestorable.
            key = f"rerun:missing{c}@S"
            obligations[key] = Obligation(
                claim_id=cid,
                clause_index=-1,
                conjunct_index=-1,
                requirement=EvidenceRequirement(kind=KINDS[0]),
            )
            reruns.append(key)
        per: list[tuple[str, ...]] = []
        for k in range(rng.randint(1, 3)):
            regs: list[Obligation] = []
            for i in range(rng.randint(1, 3)):
                kind = rng.choice(KINDS)
                indep = (regs[0].requirement.kind,) if regs and rng.random() < 0.5 else ()
                o = Obligation(
                    claim_id=cid,
                    clause_index=k,
                    conjunct_index=i,
                    requirement=EvidenceRequirement(kind=kind, independent_of=indep),
                )
                obligations[o.key] = o
                regs.append(o)
                for j in ids:
                    if cand_kind[j] is kind and rng.random() < 0.6:
                        sat[j].add(o.key)
            clause_regs.append(regs)
            per.append((*(o.key for o in regs), *reruns))
        clauses[cid] = tuple(per)

    incompatible: set[tuple[str, str, str, str]] = set()
    for regs in clause_regs:
        for o, o2 in itertools.permutations(regs, 2):
            if o2.requirement.kind not in o.requirement.independent_of:
                continue
            for j in ids:
                for j2 in ids:
                    if j == j2 or o.key not in sat[j] or o2.key not in sat[j2]:
                        continue
                    if cand_kind[j] is cand_kind[j2] or set(cand_pred[j]) & set(cand_pred[j2]):
                        incompatible.add((j, o.key, j2, o2.key))
    candidates = tuple(
        CandidateRun(
            id=j,
            producer_id=j.split("@")[0],
            subject_id="S",
            cost=cand_cost[j],
            satisfies=tuple(sorted(sat[j])),
            predictors=cand_pred[j],
            existing_evidence_id=cand_existing[j],
        )
        for j in ids
    )
    return PlanningProblem(
        snapshot_id="snap",
        claim_weights=weights,
        clauses=clauses,
        obligations={k: obligations[k] for k in sorted(obligations)},
        candidates=candidates,
        incompatible=tuple(sorted(incompatible)),
    )


def clause_assignments(problem: PlanningProblem, cid: str, k: int) -> list[frozenset[str]]:
    """Run sets of every valid full assignment of clause k (distinct runs per regular conjunct, independence).

    An independent re-implementation of the planner's matching: a clause is covered by a selection iff one of
    these run sets is a subset of it.
    """
    clause = problem.clauses[cid][k]
    inc = set(problem.incompatible)
    lists = [[c.id for c in problem.candidates if o in c.satisfies] for o in clause]
    out: list[frozenset[str]] = []
    for combo in itertools.product(*lists):
        regular = [j for o, j in zip(clause, combo, strict=True) if not o.startswith("rerun:")]
        if len(set(regular)) != len(regular):
            continue
        pairs = list(zip(clause, combo, strict=True))
        if any((j, o, j2, o2) in inc for (o, j), (o2, j2) in itertools.permutations(pairs, 2)):
            continue
        out.append(frozenset(combo))
    return out


class Coverage:
    def __init__(self, problem: PlanningProblem) -> None:
        self.problem = problem
        self.sets = {
            cid: [a for k in range(len(cls)) for a in clause_assignments(problem, cid, k)]
            for cid, cls in problem.clauses.items()
        }

    def restored(self, selected: frozenset[str]) -> frozenset[str]:
        return frozenset(cid for cid, sets in self.sets.items() if any(a <= selected for a in sets))


def restored_by(problem: PlanningProblem, selected: frozenset[str]) -> frozenset[str]:
    return Coverage(problem).restored(selected)


@dataclass(frozen=True)
class Optimum:
    weight: int  # restored criticality weight
    cost_int: int  # cost in hundredths
    restorable: frozenset[str]


def brute_force(problem: PlanningProblem, budget: float | None = None) -> Optimum:
    """Max restored weight, then min cost, over every subset of candidates (the ILP's objective)."""
    ids = [c.id for c in problem.candidates]
    cost = {c.id: round(c.cost * 100) for c in problem.candidates}
    cap = None if budget is None else round(budget * 100)
    cov = Coverage(problem)
    restorable = cov.restored(frozenset(ids))
    best: tuple[int, int] | None = None
    for r in range(len(ids) + 1):
        for subset in itertools.combinations(ids, r):
            total = sum(cost[j] for j in subset)
            if cap is not None and total > cap:
                continue
            w = sum(problem.claim_weights[c] for c in cov.restored(frozenset(subset)))
            key = (-w, total)
            if best is None or key < best:
                best = key
    assert best is not None
    return Optimum(weight=-best[0], cost_int=best[1], restorable=restorable)


def plan_cost_int(total_cost: float) -> int:
    return round(total_cost * 100)
