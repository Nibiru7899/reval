"""P2-09: claim status rules (docs/03 §3, docs/10 §4.5). One scenario per rule plus edge cases."""

import pytest

from reval.core.status import AssessInput, assess_all, assess_claim
from reval.domain import (
    DEFAULT_POLICIES,
    Assessment,
    Change,
    ChangeKind,
    ChangeSet,
    Claim,
    Comparator,
    Criticality,
    Evidence,
    EvidenceRequirement,
    EvidenceResult,
    FreshnessClass,
    Interval,
    Policy,
    Producer,
    ProducerKind,
    Provenance,
    ReasonCode,
    Requirement,
    Snapshot,
    Status,
    Verdict,
    Waiver,
)

K = ProducerKind
FX = FreshnessClass.FRESH_EXACT
OOS = FreshnessClass.FRESH_OUT_OF_SCOPE
CF = FreshnessClass.CARRY_FORWARD
INV = FreshnessClass.INVALIDATED

# limit 100 degC, "<=" ; the GE requirement uses quantity q2, limit 10 A.
LIMIT = 100.0


def _producer(pid: str, kind: ProducerKind, fidelity: int, predictors: tuple[str, ...] = ()) -> Producer:
    return Producer(
        id=pid,
        kind=kind,
        quantities=("q", "q2"),
        fidelity=fidelity,
        cost=0.0 if kind is K.WAIVER else 1.0,
        code_hash=f"code-{pid}",
        depends_on=(*predictors, "inputs"),
        predictors=predictors,
    )


PRODUCERS = {
    p.id: p
    for p in [
        _producer("ml", K.ML_PREDICTION, 1, ("tpm",)),
        _producer("ml_lptn", K.ML_PREDICTION, 1, ("lptn",)),  # shares a predictor with `sim`
        _producer("sim", K.PHYSICS_SIM, 2, ("lptn",)),
        _producer("sim_lo", K.PHYSICS_SIM, 1, ("lptn2",)),
        _producer("meas", K.MEASUREMENT, 3),
        _producer("meas2", K.MEASUREMENT, 3),
        _producer("ana", K.ANALYTIC, 3),
        _producer("ana_lo", K.ANALYTIC, 2),
        _producer("waive", K.WAIVER, 0),
    ]
}

POLICIES = {
    **DEFAULT_POLICIES,
    "meas_only": Policy(id="meas_only", alternatives=((EvidenceRequirement(kind=K.MEASUREMENT),),)),
    "two_meas": Policy(
        id="two_meas",
        alternatives=((EvidenceRequirement(kind=K.MEASUREMENT), EvidenceRequirement(kind=K.MEASUREMENT)),),
    ),
}

REQS = {
    "R": Requirement(
        id="R",
        text="t",
        quantity="q",
        op=Comparator.LE,
        limit=LIMIT,
        unit="degC",
        criticality=Criticality.LOW,
    ),
    "R-GE": Requirement(
        id="R-GE",
        text="t",
        quantity="q2",
        op=Comparator.GE,
        limit=10.0,
        unit="A",
        criticality=Criticality.LOW,
    ),
}

CLAIMS = {
    c.id: c
    for c in [
        Claim(id="C-LOW", requirement_id="R", subject_id="S1"),  # policy from criticality (low)
        Claim(id="C-MED", requirement_id="R", subject_id="S1", policy_id="medium"),
        Claim(id="C-HIGH", requirement_id="R", subject_id="S1", policy_id="high"),
        Claim(id="C-MEAS", requirement_id="R", subject_id="S1", policy_id="meas_only"),
        Claim(id="C-TWO", requirement_id="R", subject_id="S1", policy_id="two_meas"),
        Claim(id="C-GE", requirement_id="R-GE", subject_id="S1"),
        Claim(id="C-S2", requirement_id="R", subject_id="S2"),
    ]
}


def _snapshot(producers: dict[str, Producer] = PRODUCERS) -> Snapshot:
    return Snapshot.create(
        manifest_hash="m",
        quantities={"q": "degC", "q2": "A"},
        artifacts={},
        versions={},
        assumptions={},
        requirements=REQS,
        subjects={},
        claims=CLAIMS,
        policies=POLICIES,
        producers=producers,
    )


SNAP = _snapshot()


def ev(
    pid: str,
    lo: float,
    hi: float,
    *,
    subject: str = "S1",
    in_domain: bool | None = True,
    fidelity: int | None = None,
    quantity: str = "q",
    derived_from: str | None = None,
    seed: int | None = None,
    waiver_claim: str = "C-LOW",
) -> Evidence:
    prod = PRODUCERS[pid]
    unit = "degC" if quantity == "q" else "A"
    return Evidence.create(
        producer_id=pid,
        producer_kind=prod.kind,
        fidelity=prod.fidelity if fidelity is None else fidelity,
        subject_id=subject,
        result=EvidenceResult(
            quantity=quantity,
            unit=unit,
            point=(lo + hi) / 2,
            interval=Interval(lo=lo, hi=hi, unit=unit),
            uncertainty_kind="model_form",
            in_domain=in_domain,
        ),
        deps=(),
        provenance=Provenance(producer_code_hash=prod.code_hash, snapshot_id="s0", seed=seed),
        cost=prod.cost,
        derived_from_evidence=derived_from,
        waiver=(
            Waiver(
                author="a", justification="accepted by review", claim_id=waiver_claim, requirement_hash="h"
            )
            if prod.kind is K.WAIVER
            else None
        ),
    )


def PASS(pid: str, **kw: object) -> Evidence:
    return ev(pid, 80, 90, **kw)  # type: ignore[arg-type]


def FAIL(pid: str, **kw: object) -> Evidence:
    return ev(pid, 110, 120, **kw)  # type: ignore[arg-type]


def STRADDLE(pid: str, **kw: object) -> Evidence:
    return ev(pid, 95, 105, **kw)  # type: ignore[arg-type]


def fx(e: Evidence) -> AssessInput:
    return AssessInput(evidence=e, freshness=FX)


def inv(e: Evidence) -> AssessInput:
    return AssessInput(evidence=e, freshness=INV)


def cf(original: Evidence, widen: float) -> AssessInput:
    assert original.result.interval is not None
    derived = Evidence.create(
        **{
            **{name: getattr(original, name) for name in Evidence.model_fields if name != "id"},
            "result": original.result.model_copy(update={"interval": original.result.interval.widen(widen)}),
            "derived_from_evidence": original.id,
        }
    )
    return AssessInput(evidence=derived, freshness=CF, original=original)


def assess(claim_id: str, *items: AssessInput, changes: ChangeSet | None = None) -> Assessment:
    return assess_claim(CLAIMS[claim_id], SNAP, items, changes)


def codes(a: Assessment) -> list[ReasonCode]:
    return [r.code for r in a.reasons]


def reason(a: Assessment, code: ReasonCode):  # type: ignore[no-untyped-def]
    (r,) = [r for r in a.reasons if r.code is code]
    return r


def used(a: Assessment) -> set[str]:
    return {u.evidence_id for u in a.evidence if u.used_in_clause}


# ---------------------------------------------------------------- rule 1: VIOLATED


def test_fail_and_pass_is_violated_with_conflicting_evidence() -> None:
    f, p = FAIL("meas"), PASS("sim")
    a = assess("C-LOW", fx(f), fx(p))
    assert a.status is Status.VIOLATED
    r = reason(a, ReasonCode.CONFLICTING_EVIDENCE)
    assert set(r.evidence_ids) == {f.id, p.id}
    assert r.detail == {"fail_ids": [f.id], "pass_ids": [p.id]}
    assert used(a) == set()


def test_fail_alone_is_violated_without_conflict_reason() -> None:
    a = assess("C-LOW", fx(FAIL("meas")))
    assert a.status is Status.VIOLATED
    assert ReasonCode.CONFLICTING_EVIDENCE not in codes(a)


def test_fail_of_kind_not_in_policy_is_not_eligible() -> None:
    a = assess("C-MEAS", fx(FAIL("sim")), fx(PASS("meas")))
    assert a.status is Status.SUPPORTED


def test_out_of_domain_ml_fail_is_not_a_fail() -> None:
    a = assess("C-LOW", fx(FAIL("ml", in_domain=False)), fx(PASS("sim")))
    assert a.status is Status.SUPPORTED


def test_carry_forward_fail_that_stays_fail_is_violated() -> None:
    a = assess("C-LOW", cf(ev("meas", 110, 120), 2.0))
    assert a.status is Status.VIOLATED


def test_fail_beats_waiver() -> None:
    a = assess("C-LOW", fx(FAIL("meas")), fx(PASS("waive")))
    assert a.status is Status.VIOLATED


# ---------------------------------------------------------------- rule 2: WAIVED


def test_matching_waiver_is_waived() -> None:
    w = PASS("waive", waiver_claim="C-LOW")
    a = assess("C-LOW", fx(w))
    assert a.status is Status.WAIVED
    assert codes(a) == [ReasonCode.WAIVER_APPLIED]
    assert used(a) == {w.id}


def test_waiver_for_another_claim_is_ignored() -> None:
    w = PASS("waive", waiver_claim="C-MED")
    a = assess("C-LOW", fx(w))
    assert a.status is Status.INCONCLUSIVE
    assert codes(a) == [ReasonCode.NO_EVIDENCE]
    assert a.evidence == ()


def test_invalidated_waiver_does_not_apply() -> None:
    a = assess("C-LOW", inv(PASS("waive")))
    assert a.status is Status.INCONCLUSIVE
    assert codes(a) == [ReasonCode.NO_EVIDENCE]


def test_waiver_beats_lost_fail() -> None:
    a = assess("C-LOW", inv(FAIL("meas")), fx(PASS("waive")))
    assert a.status is Status.WAIVED


# ---------------------------------------------------------------- rule 3: STALE (lost fail)


def test_invalidated_fail_with_fresh_pass_is_stale_lost_fail() -> None:
    f = FAIL("meas")
    a = assess("C-LOW", inv(f), fx(PASS("sim")))
    assert a.status is Status.STALE
    r = reason(a, ReasonCode.EVIDENCE_INVALIDATED)
    assert r.evidence_ids == (f.id,)
    assert r.detail == {"lost_fail": True}


def test_invalidated_fail_alone_is_stale_lost_fail() -> None:
    a = assess("C-LOW", inv(FAIL("meas")))
    assert a.status is Status.STALE
    assert reason(a, ReasonCode.EVIDENCE_INVALIDATED).detail == {"lost_fail": True}


def test_carry_forward_fail_to_inconclusive_is_stale_lost_fail() -> None:
    item = cf(ev("meas", 101, 120), 2.0)  # recorded FAIL, inflated [99, 122] straddles
    a = assess("C-LOW", item, fx(PASS("sim")))
    assert a.status is Status.STALE
    r = reason(a, ReasonCode.EVIDENCE_INVALIDATED)
    assert r.evidence_ids == (item.evidence.id,)
    assert r.detail == {"lost_fail": True}
    (use,) = [u for u in a.evidence if u.evidence_id == item.evidence.id]
    assert use.verdict is Verdict.INCONCLUSIVE
    assert use.recorded_verdict is Verdict.FAIL
    assert use.derived_from_evidence == item.original.id  # type: ignore[union-attr]


def test_fresh_rerun_of_same_producer_supersedes_lost_fail() -> None:
    old, rerun = FAIL("meas"), PASS("meas")
    a = assess("C-LOW", inv(old), fx(rerun))
    assert a.status is Status.SUPPORTED
    assert used(a) == {rerun.id}


def test_carry_forward_rerun_also_supersedes() -> None:
    a = assess("C-LOW", inv(FAIL("meas")), cf(ev("meas", 70, 80, seed=1), 1.0))
    assert a.status is Status.SUPPORTED


def test_superseded_lost_fail_with_inconclusive_rerun_is_inconclusive_not_stale() -> None:
    a = assess("C-LOW", inv(FAIL("meas")), fx(STRADDLE("meas")))
    assert a.status is Status.INCONCLUSIVE
    assert ReasonCode.MARGIN_BELOW_UNCERTAINTY in codes(a)


def test_rerun_on_other_subject_does_not_supersede() -> None:
    a = assess("C-LOW", inv(FAIL("meas")), fx(PASS("meas", subject="S2")), fx(PASS("sim")))
    assert a.status is Status.STALE


def test_lost_fail_of_kind_not_in_policy_is_ignored() -> None:
    a = assess("C-MEAS", inv(FAIL("sim")), fx(PASS("meas")))
    assert a.status is Status.SUPPORTED


# ---------------------------------------------------------------- rule 4: SUPPORTED


def test_single_measurement_supports_low() -> None:
    p = PASS("meas")
    a = assess("C-LOW", fx(p))
    assert a.status is Status.SUPPORTED
    assert a.satisfied_clause == 2
    assert reason(a, ReasonCode.POLICY_SATISFIED).evidence_ids == (p.id,)
    assert used(a) == {p.id}


def test_lowest_clause_index_wins() -> None:
    a = assess("C-LOW", fx(PASS("meas")), fx(PASS("ml")))
    assert a.satisfied_clause == 0


def test_fresh_out_of_scope_and_carry_forward_pass_support() -> None:
    assert assess("C-LOW", AssessInput(evidence=PASS("meas"), freshness=OOS)).status is Status.SUPPORTED
    a = assess("C-LOW", cf(ev("meas", 80, 90), 2.0))
    assert a.status is Status.SUPPORTED
    assert a.evidence[0].freshness is CF
    assert a.evidence[0].interval_used == Interval(lo=78, hi=92, unit="degC")


def test_medium_needs_in_domain_ml_and_independent_physics() -> None:
    m, s = PASS("ml"), PASS("sim")
    a = assess("C-MED", fx(m), fx(s))
    assert a.status is Status.SUPPORTED
    assert a.satisfied_clause == 0
    assert used(a) == {m.id, s.id}


def test_medium_ml_and_physics_sharing_a_predictor_are_not_independent() -> None:
    a = assess("C-MED", fx(PASS("ml_lptn")), fx(PASS("sim")))
    assert a.status is Status.INCONCLUSIVE
    assert ReasonCode.POLICY_UNMET in codes(a)


def test_medium_picks_the_independent_ml_when_both_exist() -> None:
    m = PASS("ml")
    a = assess("C-MED", fx(PASS("ml_lptn")), fx(m), fx(PASS("sim")))
    assert a.status is Status.SUPPORTED
    assert m.id in used(a)


def test_medium_physics_alone_is_policy_unmet() -> None:
    a = assess("C-MED", fx(PASS("sim")))
    assert a.status is Status.INCONCLUSIVE
    assert codes(a) == [ReasonCode.POLICY_UNMET]


def test_medium_out_of_domain_ml_is_inconclusive() -> None:
    a = assess("C-MED", fx(PASS("ml", in_domain=False)), fx(PASS("sim")))
    assert a.status is Status.INCONCLUSIVE
    assert set(codes(a)) == {ReasonCode.OUT_OF_DOMAIN, ReasonCode.POLICY_UNMET}


def test_independence_fails_closed_for_unknown_producer() -> None:
    producers = {k: v for k, v in PRODUCERS.items() if k != "ml"}
    snap = _snapshot(producers)
    a = assess_claim(CLAIMS["C-MED"], snap, [fx(PASS("ml")), fx(PASS("sim"))])
    assert a.status is Status.INCONCLUSIVE


def test_high_respects_min_fidelity_of_physics() -> None:
    low = assess("C-HIGH", fx(PASS("sim_lo")), fx(PASS("ml")))
    assert low.status is Status.INCONCLUSIVE
    ok = assess("C-HIGH", fx(PASS("sim")), fx(PASS("ml")))
    assert ok.status is Status.SUPPORTED
    assert ok.satisfied_clause == 1


@pytest.mark.parametrize(("pid", "status"), [("ana_lo", Status.INCONCLUSIVE), ("ana", Status.SUPPORTED)])
def test_medium_analytic_min_fidelity(pid: str, status: Status) -> None:
    a = assess("C-MED", fx(PASS(pid)))
    assert a.status is status


def test_clause_needs_distinct_evidence() -> None:
    p1 = PASS("meas")
    assert assess("C-TWO", fx(p1)).status is Status.INCONCLUSIVE
    a = assess("C-TWO", fx(p1), fx(PASS("meas2")))
    assert a.status is Status.SUPPORTED


def test_ge_requirement() -> None:
    assert assess("C-GE", fx(ev("meas", 10, 12, quantity="q2"))).status is Status.SUPPORTED  # inclusive
    assert assess("C-GE", fx(ev("meas", 5, 9.9, quantity="q2"))).status is Status.VIOLATED
    assert assess("C-GE", fx(ev("meas", 9, 11, quantity="q2"))).status is Status.INCONCLUSIVE


# ---------------------------------------------------------------- rule 5: STALE


def test_invalidated_only_support_is_stale() -> None:
    p = PASS("meas")
    a = assess("C-LOW", inv(p))
    assert a.status is Status.STALE
    r = reason(a, ReasonCode.EVIDENCE_INVALIDATED)
    assert r.evidence_ids == (p.id,)
    assert r.detail == {"lost_fail": False}
    assert used(a) == set()
    assert a.satisfied_clause is None


def test_carried_pass_widened_to_inconclusive_is_stale() -> None:
    item = cf(ev("meas", 80, 98), 5.0)  # recorded PASS, inflated [75, 103] straddles
    a = assess("C-LOW", item)
    assert a.status is Status.STALE
    assert reason(a, ReasonCode.EVIDENCE_INVALIDATED).evidence_ids == (item.evidence.id,)


def test_stale_medium_lists_only_the_changed_item() -> None:
    m, s = PASS("ml"), PASS("sim")
    a = assess("C-MED", inv(m), fx(s))
    assert a.status is Status.STALE
    assert reason(a, ReasonCode.EVIDENCE_INVALIDATED).evidence_ids == (m.id,)


def test_superseded_pass_does_not_make_stale() -> None:
    a = assess("C-LOW", inv(PASS("meas")), fx(STRADDLE("meas")))
    assert a.status is Status.INCONCLUSIVE


def test_invalidated_inconclusive_is_not_stale() -> None:
    a = assess("C-LOW", inv(STRADDLE("meas")))
    assert a.status is Status.INCONCLUSIVE
    assert codes(a) == [ReasonCode.NO_EVIDENCE]


# ---------------------------------------------------------------- rule 6: INCONCLUSIVE


def test_no_evidence() -> None:
    a = assess("C-LOW")
    assert a.status is Status.INCONCLUSIVE
    assert codes(a) == [ReasonCode.NO_EVIDENCE]
    assert a.evidence == ()


def test_evidence_for_other_subject_or_quantity_is_ignored() -> None:
    a = assess("C-LOW", fx(PASS("meas", subject="S2")), fx(ev("meas", 1, 2, quantity="q2")))
    assert codes(a) == [ReasonCode.NO_EVIDENCE]
    assert a.evidence == ()


def test_interval_straddling_limit_is_margin_below_uncertainty() -> None:
    s = STRADDLE("meas")
    a = assess("C-LOW", fx(s))
    assert a.status is Status.INCONCLUSIVE
    assert codes(a) == [ReasonCode.MARGIN_BELOW_UNCERTAINTY]
    assert a.reasons[0].evidence_ids == (s.id,)


def test_out_of_domain_ml_alone() -> None:
    a = assess("C-LOW", fx(PASS("ml", in_domain=None)))
    assert a.status is Status.INCONCLUSIVE
    assert codes(a) == [ReasonCode.OUT_OF_DOMAIN]


# ---------------------------------------------------------------- inputs, reasons, hashing


def test_carry_forward_without_original_raises() -> None:
    item = cf(PASS("meas"), 1.0)
    with pytest.raises(ValueError, match="CARRY_FORWARD"):
        assess("C-LOW", AssessInput(evidence=item.evidence, freshness=CF))


def test_carry_forward_without_derived_from_raises() -> None:
    p = PASS("meas")
    with pytest.raises(ValueError, match="CARRY_FORWARD"):
        assess("C-LOW", AssessInput(evidence=p, freshness=CF, original=p))


def test_carry_forward_with_wrong_original_raises() -> None:
    item = cf(PASS("meas"), 1.0)
    with pytest.raises(ValueError, match="original"):
        assess("C-LOW", AssessInput(evidence=item.evidence, freshness=CF, original=PASS("sim")))


def test_duplicate_items_are_deduplicated_but_conflicts_raise() -> None:
    p = PASS("meas")
    assert assess("C-LOW", fx(p), fx(p)) == assess("C-LOW", fx(p))
    with pytest.raises(ValueError, match="twice"):
        assess("C-LOW", fx(p), inv(p))


def test_requirement_changed_is_informational() -> None:
    changes = ChangeSet(
        from_snapshot="a",
        to_snapshot="b",
        changes=(Change(kind=ChangeKind.REQUIREMENT_CHANGED, target="R"),),
    )
    a = assess("C-LOW", fx(PASS("meas")), changes=changes)
    assert a.status is Status.SUPPORTED
    assert codes(a) == [ReasonCode.POLICY_SATISFIED, ReasonCode.REQUIREMENT_CHANGED]
    other = ChangeSet(
        from_snapshot="a",
        to_snapshot="b",
        changes=(Change(kind=ChangeKind.REQUIREMENT_CHANGED, target="R-GE"),),
    )
    assert codes(assess("C-LOW", fx(PASS("meas")), changes=other)) == [ReasonCode.POLICY_SATISFIED]


def test_evidence_uses_sorted_by_id() -> None:
    a = assess("C-LOW", fx(PASS("sim")), fx(PASS("meas")), fx(PASS("ml")))
    ids = [u.evidence_id for u in a.evidence]
    assert ids == sorted(ids)


def test_input_hash_is_deterministic_and_order_independent() -> None:
    items = [fx(PASS("sim")), inv(FAIL("meas")), cf(ev("ml", 70, 80), 1.0)]
    a = assess("C-MED", *items)
    b = assess("C-MED", *reversed(items))
    assert a == b
    assert a.input_hash == assess("C-MED", *items).input_hash
    assert len(a.input_hash) == 64


def test_input_hash_ignores_other_subjects_and_tracks_freshness() -> None:
    p = PASS("meas")
    base = assess("C-LOW", fx(p))
    assert assess("C-LOW", fx(p), fx(PASS("sim", subject="S2"))).input_hash == base.input_hash
    assert assess("C-LOW", AssessInput(evidence=p, freshness=OOS)).input_hash != base.input_hash
    assert assess("C-MED", fx(p)).input_hash != base.input_hash  # different claim and policy


def test_assess_all_covers_every_claim_sorted() -> None:
    items = [fx(PASS("meas")), fx(FAIL("meas2", subject="S2"))]
    out = assess_all(SNAP, items)
    assert list(out) == sorted(CLAIMS)
    assert out["C-LOW"].status is Status.SUPPORTED
    assert out["C-S2"].status is Status.VIOLATED
    assert out["C-GE"].status is Status.INCONCLUSIVE
    assert all(a.snapshot_id == SNAP.id for a in out.values())
    assert out == assess_all(SNAP, list(reversed(items)))


def test_interval_used_for_exact_and_point_only_results() -> None:
    exact = Evidence.create(
        **{
            **{n: getattr(PASS("ana"), n) for n in Evidence.model_fields if n != "id"},
            "result": EvidenceResult(quantity="q", unit="degC", point=99.0, uncertainty_kind="exact"),
        }
    )
    point_only = exact.model_copy(update={"producer_id": "meas", "producer_kind": K.MEASUREMENT})
    point_only = Evidence.create(
        **{
            **{n: getattr(point_only, n) for n in Evidence.model_fields if n != "id"},
            "result": EvidenceResult(quantity="q", unit="degC", point=99.0, uncertainty_kind="sensor"),
        }
    )
    a = assess("C-LOW", fx(exact), fx(point_only))
    assert a.status is Status.SUPPORTED
    by_id = {u.evidence_id: u for u in a.evidence}
    assert by_id[exact.id].interval_used == Interval(lo=99.0, hi=99.0, unit="degC")
    assert by_id[point_only.id].interval_used is None
    assert by_id[point_only.id].verdict is Verdict.INCONCLUSIVE
