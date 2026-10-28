"""Evidence oracle: the B0 "rerun everything" run and the truly-affected labels (docs/06 section 2).

B0 runs every producer for every claim subject in a snapshot and assesses with only that fresh evidence.
A claim is truly affected if its B0 status differs between S and S', or some evidence value referenced by
ANY clause of its policy (used or not) moved by more than epsilon, appeared or disappeared.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from bench.harness.cache import ProducerResultCache
from reval.core.status import AssessInput, assess_all
from reval.domain.assessment import Assessment
from reval.domain.evidence import Evidence
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass, Status
from reval.services.project import Project


@dataclass(frozen=True)
class ClaimOutcome:
    """B0 result for one claim: status plus the values any policy clause could reference."""

    status: Status
    quantity: str
    values: Mapping[str, float]  # "producer|subject|quantity" -> point value


@dataclass(frozen=True)
class B0Result:
    outcomes: Mapping[str, ClaimOutcome]
    assessments: Mapping[str, Assessment]
    evidence: tuple[Evidence, ...]
    runs: tuple[tuple[str, str], ...]
    cost: float  # full cost of B0, independent of cache hits


def epsilon_from_halfwidths(
    halfwidths: Mapping[str, Sequence[float]], factor: float = 0.1
) -> dict[str, float]:
    """Pre-registered epsilon per target: ``factor`` times the median conformal half-width q-hat."""
    return {q: factor * statistics.median(v) for q, v in halfwidths.items()}


def b0_runs(snapshot: Snapshot, project: Project) -> list[tuple[str, str]]:
    """Every (producer, subject) that yields a quantity some claim on that subject needs."""
    needed: dict[str, set[str]] = {}
    for claim in snapshot.claims.values():
        needed.setdefault(claim.subject_id, set()).add(snapshot.requirements[claim.requirement_id].quantity)
    runs: list[tuple[str, str]] = []
    for rp in project.registry.all():
        for sid in sorted(needed):
            if not needed[sid] & set(rp.meta.quantities):
                continue
            if rp.available_for is not None and not rp.available_for(snapshot.subjects[sid]):
                continue
            runs.append((rp.meta.id, sid))
    return sorted(runs)


def _values(snapshot: Snapshot, claim_id: str, evidence: Sequence[Evidence]) -> dict[str, float]:
    """Points of evidence on the claim's subject/quantity whose kind appears in ANY policy clause."""
    claim = snapshot.claims[claim_id]
    quantity = snapshot.requirements[claim.requirement_id].quantity
    kinds = {r.kind for alt in snapshot.policy_for(claim_id).alternatives for r in alt}
    out: dict[str, float] = {}
    for e in evidence:
        if e.subject_id != claim.subject_id or e.result.quantity != quantity or e.producer_kind not in kinds:
            continue
        if e.result.point is not None:
            out[f"{e.producer_id}|{e.subject_id}|{e.result.quantity}"] = float(e.result.point)
    return out


def assess_evidence(snapshot: Snapshot, evidence: Sequence[Evidence]) -> B0Result:
    """Assess ``evidence`` as fresh-exact at ``snapshot`` (it was produced there)."""
    items = [AssessInput(e, FreshnessClass.FRESH_EXACT) for e in evidence]
    assessments = assess_all(snapshot, items)
    outcomes = {
        cid: ClaimOutcome(
            a.status,
            snapshot.requirements[snapshot.claims[cid].requirement_id].quantity,
            _values(snapshot, cid, evidence),
        )
        for cid, a in assessments.items()
    }
    return B0Result(outcomes, assessments, tuple(evidence), (), 0.0)


def run_b0(
    project: Project,
    snapshot: Snapshot,
    cache: ProducerResultCache,
    settings: ReValSettings = DEFAULT_SETTINGS,
) -> B0Result:
    """Rerun every producer for every claim subject (through the shared cache) and assess."""
    runs = b0_runs(snapshot, project)
    evidence: list[Evidence] = []
    for pid, sid in runs:
        got, _ = cache.run(project, snapshot, pid, sid, settings)
        evidence.extend(got)
    res = assess_evidence(snapshot, evidence)
    cost = sum(snapshot.producers[pid].cost for pid, _ in runs)
    return B0Result(res.outcomes, res.assessments, res.evidence, tuple(runs), cost)


def truly_affected(
    before: Mapping[str, ClaimOutcome],
    after: Mapping[str, ClaimOutcome],
    epsilon: Mapping[str, float],
) -> dict[str, bool]:
    """Evidence-oracle labels per claim. A quantity without a pre-registered epsilon is an error."""
    labels: dict[str, bool] = {}
    for cid in sorted(set(before) | set(after)):
        b, a = before.get(cid), after.get(cid)
        if b is None or a is None:
            labels[cid] = True  # claim exists on one side only: fail closed
            continue
        if b.status != a.status:
            labels[cid] = True
            continue
        eps = epsilon[a.quantity]
        moved = set(b.values) ^ set(a.values) != set()
        moved = moved or any(abs(a.values[k] - b.values[k]) > eps for k in b.values.keys() & a.values.keys())
        labels[cid] = moved
    return labels
