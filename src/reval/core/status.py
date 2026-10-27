"""Claim status (docs/03-domain-model.md §3, docs/04-algorithms.md A6, docs/10-interfaces.md §4.5). Pure.

Status is history-free (D4): it is a function of the snapshot and the evidence items with their
freshness classes only.
"""

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from reval.core.canonical import canonical_json, sha256_hex
from reval.core.verdicts import verdict, verdict_interval
from reval.domain.assessment import Assessment, EvidenceUse, Reason
from reval.domain.changes import ChangeKind, ChangeSet
from reval.domain.engineering import Claim, Requirement
from reval.domain.evidence import Evidence, ProducerKind
from reval.domain.policies import EvidenceRequirement, Policy
from reval.domain.quantities import Interval
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass, ReasonCode, Status, Verdict

FRESH_CLASSES: frozenset[FreshnessClass] = frozenset(
    {FreshnessClass.FRESH_EXACT, FreshnessClass.FRESH_OUT_OF_SCOPE, FreshnessClass.CARRY_FORWARD}
)


@dataclass(frozen=True)
class AssessInput:
    evidence: Evidence  # for CARRY_FORWARD: the derived e' (never the original e)
    freshness: FreshnessClass
    original: Evidence | None = (
        None  # for CARRY_FORWARD: the original e (to compute recorded_verdict); else None
    )


@dataclass(frozen=True)
class _Item:
    """One input item evaluated against the claim's requirement."""

    inp: AssessInput
    current: Verdict
    current_reasons: tuple[Reason, ...]
    recorded: Verdict
    eligible: bool
    superseded: bool

    @property
    def ev(self) -> Evidence:
        return self.inp.evidence

    @property
    def id(self) -> str:
        return self.inp.evidence.id

    @property
    def is_waiver(self) -> bool:
        return self.inp.evidence.producer_kind is ProducerKind.WAIVER


def _policy(claim: Claim, snapshot: Snapshot, req: Requirement) -> Policy:
    return snapshot.policies[claim.policy_id or req.criticality.value]


def _validate(inp: AssessInput) -> None:
    if inp.freshness is FreshnessClass.CARRY_FORWARD:
        if inp.evidence.derived_from_evidence is None or inp.original is None:
            raise ValueError(
                f"CARRY_FORWARD item {inp.evidence.id} needs derived_from_evidence and the original evidence"
            )
        if inp.evidence.derived_from_evidence != inp.original.id:
            raise ValueError(
                f"CARRY_FORWARD item {inp.evidence.id} derives from {inp.evidence.derived_from_evidence}, "
                f"but original {inp.original.id} was passed"
            )


def _relevant(claim: Claim, req: Requirement, items: Sequence[AssessInput]) -> list[AssessInput]:
    """Items for this claim's subject and quantity (waivers only for this claim), deduped, sorted by id."""
    by_id: dict[str, AssessInput] = {}
    for inp in items:
        e = inp.evidence
        if e.subject_id != claim.subject_id or e.result.quantity != req.quantity:
            continue
        if e.waiver is not None and e.waiver.claim_id != claim.id:
            continue
        prev = by_id.get(e.id)
        if prev is not None and prev != inp:
            raise ValueError(f"evidence {e.id} passed twice with different freshness or original")
        by_id[e.id] = inp
    return [by_id[k] for k in sorted(by_id)]


def _evaluate(
    relevant: list[AssessInput], req: Requirement, policy_kinds: frozenset[ProducerKind]
) -> list[_Item]:
    fresh_producers = {inp.evidence.producer_id for inp in relevant if inp.freshness in FRESH_CLASSES}
    out: list[_Item] = []
    for inp in relevant:
        e = inp.evidence
        current, reasons = verdict(e, req)
        if inp.freshness is FreshnessClass.CARRY_FORWARD:
            assert inp.original is not None  # checked in _validate
            recorded, _ = verdict(inp.original, req)
        else:
            recorded = current
        fresh = inp.freshness in FRESH_CLASSES
        is_waiver = e.producer_kind is ProducerKind.WAIVER
        out.append(
            _Item(
                inp=inp,
                current=current,
                current_reasons=reasons,
                recorded=recorded,
                eligible=fresh and (is_waiver or e.producer_kind in policy_kinds),
                superseded=inp.freshness is FreshnessClass.INVALIDATED and e.producer_id in fresh_producers,
            )
        )
    return out


def _independent(a: Evidence, b: Evidence, snapshot: Snapshot) -> bool:
    """D6: different producer kind and disjoint predictors. Unknown producers: never independent."""
    if a.producer_kind is b.producer_kind:
        return False
    pa, pb = snapshot.producers.get(a.producer_id), snapshot.producers.get(b.producer_id)
    if pa is None or pb is None:
        return False
    return not set(pa.predictors) & set(pb.predictors)


def _match(
    policy: Policy,
    pool: list[_Item],
    verdict_of: Callable[[_Item], Verdict],
    snapshot: Snapshot,
    accept: Callable[[tuple[_Item, ...]], bool] = lambda _: True,
) -> tuple[int, tuple[_Item, ...]] | None:
    """First valid assignment (lowest clause index, then lexicographic ids) of distinct PASS items."""

    def candidates(req: EvidenceRequirement) -> list[_Item]:
        return [
            it
            for it in pool  # pool is sorted by evidence id
            if verdict_of(it) is Verdict.PASS
            and it.ev.producer_kind is req.kind
            and it.ev.fidelity >= req.min_fidelity
            and (not req.in_domain or it.ev.result.in_domain is True)
        ]

    for k, clause in enumerate(policy.alternatives):
        lists = [candidates(r) for r in clause]
        for combo in itertools.product(*lists):
            if len({it.id for it in combo}) != len(combo):
                continue
            ok = all(
                _independent(combo[i].ev, combo[j].ev, snapshot)
                for i, r in enumerate(clause)
                for j in range(len(clause))
                if j != i and combo[j].ev.producer_kind in r.independent_of
            )
            if ok and accept(combo):
                return k, combo
    return None


def _interval_used(e: Evidence) -> Interval | None:
    bounds = verdict_interval(e)
    if bounds is None:
        return None
    return Interval(lo=bounds[0], hi=bounds[1], unit=e.result.unit)


def _input_hash(
    claim: Claim, req: Requirement, policy: Policy, relevant: list[AssessInput], snapshot: Snapshot
) -> str:
    rows = sorted(
        (
            [
                inp.evidence.id,
                inp.freshness.value,
                inp.evidence.result.interval,
                inp.original.id if inp.original is not None else None,
            ]
            for inp in relevant
        ),
        key=canonical_json,
    )
    # Predictors decide independence (D6), so they are inputs too, even though they rarely change alone.
    predictors = {
        pid: list(snapshot.producers[pid].predictors)
        for pid in sorted({inp.evidence.producer_id for inp in relevant})
        if pid in snapshot.producers
    }
    return sha256_hex(
        canonical_json(
            {"claim": claim, "requirement": req, "policy": policy, "items": rows, "predictors": predictors}
        )
    )


def _ids(items: Sequence[_Item]) -> tuple[str, ...]:
    return tuple(sorted({it.id for it in items}))


def assess_claim(
    claim: Claim, snapshot: Snapshot, items: Sequence[AssessInput], changes: ChangeSet | None = None
) -> Assessment:
    """Evaluate the history-free status rules for one claim (docs/03 §3); first matching rule wins."""
    for inp in items:
        _validate(inp)
    req = snapshot.requirements[claim.requirement_id]
    policy = _policy(claim, snapshot, req)
    policy_kinds = frozenset(r.kind for clause in policy.alternatives for r in clause)
    relevant = _relevant(claim, req, items)
    evaluated = _evaluate(relevant, req, policy_kinds)
    eligible = [it for it in evaluated if it.eligible]

    status: Status
    reasons: list[Reason] = []
    used: set[str] = set()
    satisfied_clause: int | None = None

    fails = [it for it in eligible if it.current is Verdict.FAIL]
    passes = [it for it in eligible if it.current is Verdict.PASS]
    waivers = [it for it in eligible if it.is_waiver]
    lost_fails = [
        it
        for it in evaluated
        if not it.superseded
        and it.ev.producer_kind in policy_kinds
        and it.recorded is Verdict.FAIL
        and (
            it.inp.freshness is FreshnessClass.INVALIDATED
            or (it.inp.freshness is FreshnessClass.CARRY_FORWARD and it.current is not Verdict.FAIL)
        )
    ]

    # Rule 1: fail dominates.
    if fails:
        status = Status.VIOLATED
        reasons.append(
            Reason(
                code=ReasonCode.REQUIREMENT_VIOLATED,
                message="fresh evidence shows the requirement is not met",
                evidence_ids=_ids(fails),
            )
        )
        if passes:
            reasons.append(
                Reason(
                    code=ReasonCode.CONFLICTING_EVIDENCE,
                    message="fresh evidence both fails and passes the requirement; investigate",
                    evidence_ids=_ids(fails + passes),
                    detail={"fail_ids": list(_ids(fails)), "pass_ids": list(_ids(passes))},
                )
            )
    # Rule 2.
    elif waivers:
        status = Status.WAIVED
        used.update(it.id for it in waivers)
        reasons.append(
            Reason(
                code=ReasonCode.WAIVER_APPLIED,
                message=f"a waiver for claim {claim.id} is in effect",
                evidence_ids=_ids(waivers),
            )
        )
    # Rule 3: a change must never turn a refuted claim into an accepted one without new evidence.
    elif lost_fails:
        status = Status.STALE
        reasons.append(
            Reason(
                code=ReasonCode.EVIDENCE_INVALIDATED,
                message="evidence that failed the requirement lost freshness; a rerun is required",
                evidence_ids=_ids(lost_fails),
                detail={"lost_fail": True},
            )
        )
    else:
        fresh_pool = [it for it in eligible if not it.is_waiver]
        match = _match(policy, fresh_pool, lambda it: it.current, snapshot)
        if match is not None:
            # Rule 4.
            status = Status.SUPPORTED
            satisfied_clause, combo = match
            used.update(it.id for it in combo)
            reasons.append(
                Reason(
                    code=ReasonCode.POLICY_SATISFIED,
                    message=f"policy {policy.id} clause {satisfied_clause} is satisfied by recorded evidence",
                    evidence_ids=_ids(combo),
                )
            )
        else:
            stale = _stale_match(policy, evaluated, fresh_pool, snapshot)
            if stale is not None:
                # Rule 5: support was lost to invalidation or to carry-forward inflation.
                status = Status.STALE
                reasons.append(
                    Reason(
                        code=ReasonCode.EVIDENCE_INVALIDATED,
                        message="supporting evidence lost freshness or was widened by carry-forward",
                        evidence_ids=_ids(stale),
                        detail={"lost_fail": False},
                    )
                )
            else:
                # Rule 6.
                status = Status.INCONCLUSIVE
                if not eligible:
                    reasons.append(
                        Reason(
                            code=ReasonCode.NO_EVIDENCE, message=f"no eligible evidence for claim {claim.id}"
                        )
                    )
                else:
                    for it in eligible:
                        reasons.extend(it.current_reasons)
                    if passes:
                        reasons.append(
                            Reason(
                                code=ReasonCode.POLICY_UNMET,
                                message=f"passing evidence exists but no clause of policy {policy.id} is met",
                                evidence_ids=_ids(passes),
                            )
                        )

    if changes is not None and any(
        c.kind is ChangeKind.REQUIREMENT_CHANGED and c.target == req.id for c in changes.changes
    ):
        reasons.append(
            Reason(
                code=ReasonCode.REQUIREMENT_CHANGED,
                message=f"requirement {req.id} changed in this diff",
            )
        )

    uses = tuple(
        EvidenceUse(
            evidence_id=it.id,
            verdict=it.current,
            freshness=it.inp.freshness,
            interval_used=_interval_used(it.ev),
            used_in_clause=it.id in used,
            derived_from_evidence=it.ev.derived_from_evidence,
            recorded_verdict=it.recorded,
        )
        for it in evaluated
    )
    return Assessment(
        claim_id=claim.id,
        snapshot_id=snapshot.id,
        status=status,
        reasons=_dedupe_reasons(reasons),
        evidence=uses,
        satisfied_clause=satisfied_clause,
        input_hash=_input_hash(claim, req, policy, relevant, snapshot),
    )


def _stale_match(
    policy: Policy, evaluated: list[_Item], fresh_pool: list[_Item], snapshot: Snapshot
) -> tuple[_Item, ...] | None:
    """Rule 5: matching with non-superseded INVALIDATED and CARRY_FORWARD items at their recorded verdicts.

    Returns the items whose recorded verdict made the difference, or None if no clause would be satisfied.
    """
    revived = [it for it in evaluated if it.inp.freshness is FreshnessClass.INVALIDATED and not it.superseded]
    pool = sorted(fresh_pool + [it for it in revived if not it.is_waiver], key=lambda it: it.id)

    def at_recorded(it: _Item) -> Verdict:
        if it.inp.freshness in (FreshnessClass.INVALIDATED, FreshnessClass.CARRY_FORWARD):
            return it.recorded
        return it.current

    def changed(it: _Item) -> bool:
        return it.inp.freshness is FreshnessClass.INVALIDATED or it.current is not Verdict.PASS

    match = _match(policy, pool, at_recorded, snapshot, accept=lambda combo: any(changed(it) for it in combo))
    if match is None:
        return None
    return tuple(it for it in match[1] if changed(it))


def _dedupe_reasons(reasons: list[Reason]) -> tuple[Reason, ...]:
    # Insertion order is deterministic: rule reason first, then per-item reasons in evidence-id order.
    seen: dict[bytes, Reason] = {}
    for r in reasons:
        seen.setdefault(canonical_json(r), r)
    return tuple(seen.values())


def assess_all(
    snapshot: Snapshot, items: Sequence[AssessInput], changes: ChangeSet | None = None
) -> dict[str, Assessment]:
    """Assess every claim of ``snapshot``; keys (claim ids) are in sorted order."""
    return {
        cid: assess_claim(snapshot.claims[cid], snapshot, items, changes) for cid in sorted(snapshot.claims)
    }
