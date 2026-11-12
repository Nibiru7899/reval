"""P3-03: freshness skeleton: hard failures, exact shortcut, relevance (a)-(f), invalidation."""

from typing import Any

from reval.core.canonical import content_id
from reval.core.diff import diff_snapshots
from reval.core.freshness import FreshnessResult, classify_all, classify_evidence
from reval.domain.changes import Change, ChangeKind, ChangeSet
from reval.domain.evidence import Evidence, EvidenceResult, Producer, ProducerKind, Provenance, Waiver
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass, ReasonCode
from tests.helpers.mini_fresh import append, edit, pid, reev, resnap, run, run_all

F = FreshnessClass
K = ChangeKind


def _classify(e: Evidence, old: Snapshot, new: Snapshot) -> FreshnessResult:
    return classify_evidence(e, old, new, diff_snapshots(old, new))


def _codes(fr: FreshnessResult) -> set[ReasonCode]:
    return {r.code for r in fr.reasons}


def test_no_change_is_fresh_exact(mini: Any) -> None:
    s0 = mini.snapshot()
    for e in run_all(mini, s0).values():
        fr = _classify(e, s0, s0)
        assert (fr.cls, fr.reasons, fr.inflation, fr.relevant_changes) == (F.FRESH_EXACT, (), 0.0, ())


def test_unrelated_field_fresh_related_field_missing_tolerance(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    edit(mini, "params/params.yaml", "d_mm: 30.00", "d_mm: 30.01")
    assert _classify(sim, s0, mini.snapshot()).cls is F.FRESH_EXACT
    edit(mini, "params/params.yaml", "gain: 2.0", "gain: 2.1")
    fr = _classify(sim, s0, mini.snapshot())
    assert fr.cls is F.INVALIDATED
    assert _codes(fr) == {ReasonCode.MISSING_TOLERANCE}
    assert [c.target for c in fr.relevant_changes] == ["params#/sim/gain"]


def test_whole_artifact_dep_invalidated_by_any_change(mini: Any) -> None:
    s0 = mini.snapshot()
    ml = run(mini, s0, "predict_temp", "S1")
    edit(mini, "models/surrogate.json", '"slope": 10.0', '"slope": 10.5')
    fr = _classify(ml, s0, mini.snapshot())
    assert fr.cls is F.INVALIDATED
    assert _codes(fr) == {ReasonCode.EVIDENCE_INVALIDATED}


def test_producer_code_change_invalidates_only_that_producer(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    p = pid(mini, "sim_temp")
    s1 = resnap(s0, producers={**s0.producers, p: s0.producers[p].model_copy(update={"code_hash": "c" * 64})})
    fr = _classify(ev[("sim_temp", "S1")], s0, s1)
    assert fr.cls is F.INVALIDATED and _codes(fr) == {ReasonCode.EVIDENCE_INVALIDATED}
    assert _classify(ev[("predict_temp", "S1")], s0, s1).cls is F.FRESH_EXACT


def test_depends_on_change_invalidates(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    p = pid(mini, "sim_temp")
    prod = s0.producers[p].model_copy(update={"depends_on": ("params#/load/scale",)})
    assert _classify(sim, s0, resnap(s0, producers={**s0.producers, p: prod})).cls is F.INVALIDATED


def _cs(s: Snapshot, *changes: Change) -> ChangeSet:
    return ChangeSet(from_snapshot=s.id, to_snapshot=s.id, changes=changes)


def test_unknown_on_dep_artifact_invalidates_unrelated_is_fresh(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    sim, shaft = ev[("sim_temp", "S1")], ev[("shaft_check", "D1")]
    on_params = _cs(s0, Change(kind=K.UNKNOWN, target="params"))
    fr = classify_evidence(sim, s0, s0, on_params)
    assert fr.cls is F.INVALIDATED and _codes(fr) == {ReasonCode.UNKNOWN_CHANGE}
    assert classify_evidence(shaft, s0, s0, on_params).cls is F.INVALIDATED
    on_other = _cs(s0, Change(kind=K.UNKNOWN, target="surrogate"))
    assert classify_evidence(sim, s0, s0, on_other).cls is F.FRESH_EXACT
    assert classify_evidence(shaft, s0, s0, on_other).cls is F.FRESH_EXACT


def test_unknown_on_upstream_of_dep_invalidates(mini: Any) -> None:
    s0 = mini.snapshot()
    ml = run(mini, s0, "predict_temp", "S1")  # depends on surrogate, derived from data
    fr = classify_evidence(ml, s0, s0, _cs(s0, Change(kind=K.UNKNOWN, target="data#/whatever")))
    assert fr.cls is F.INVALIDATED


def test_unknown_with_unparseable_target_invalidates_everything(mini: Any) -> None:
    s0 = mini.snapshot()
    cs = _cs(s0, Change(kind=K.UNKNOWN, target="quantity:temp_peak"))
    for e in run_all(mini, s0).values():
        fr = classify_evidence(e, s0, s0, cs)
        assert fr.cls is F.INVALIDATED and _codes(fr) == {ReasonCode.UNKNOWN_CHANGE}


def test_subject_change_invalidates_evidence_on_that_subject(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    edit(mini, "reval.yaml", "load: [1.0, 2.0]", "load: [1.0, 2.1]")
    s1 = mini.snapshot()
    for (name, sid), e in ev.items():
        fr = _classify(e, s0, s1)
        if sid == "S1":
            assert fr.cls is F.INVALIDATED, name
            assert [c.kind for c in fr.relevant_changes] == [K.SUBJECT_CHANGED]
        else:
            assert fr.cls is F.FRESH_EXACT, (name, sid)


def test_scoped_assumption_change_invalidates(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    edit(mini, "reval.yaml", "bounds: [0.5, 1.5]", "bounds: [0.5, 1.4]")  # A-sim-sens
    s1 = mini.snapshot()
    assert _classify(ev[("sim_temp", "S1")], s0, s1).cls is F.INVALIDATED
    assert _classify(ev[("predict_temp", "S1")], s0, s1).cls is F.FRESH_EXACT


def test_requirement_policy_claim_changes_are_not_relevant(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    edit(
        mini,
        "reval.yaml",
        "limit: 80, unit: degC, criticality: medium",
        "limit: 85, unit: degC, criticality: medium",
    )
    edit(mini, "reval.yaml", "  - {id: C-S2-TEMP, requirement: R-TEMP, subject: S2}\n", "")
    s1 = mini.snapshot()
    kinds = {c.kind for c in diff_snapshots(s0, s1).changes}
    assert kinds == {K.REQUIREMENT_CHANGED, K.CLAIM_CHANGED}
    for e in ev.values():
        assert _classify(e, s0, s1).cls is F.FRESH_EXACT


def test_upstream_data_change_invalidates_surrogate_evidence(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    append(mini, "data/data.csv", "g4,5.0,70.0\n")
    s1 = mini.snapshot()
    fr = _classify(ev[("predict_temp", "S1")], s0, s1)
    assert fr.cls is F.INVALIDATED
    assert {c.kind for c in fr.relevant_changes} == {K.ROWS_ADDED, K.ARTIFACT_CHANGED}
    assert _classify(ev[("shaft_check", "D1")], s0, s1).cls is F.FRESH_EXACT


def test_pointer_dep_on_derived_params_invalidated_by_upstream_change(mini: Any) -> None:
    # D3: own-only field hashes stay equal when only an upstream artifact changes; the shortcut must not fire.
    edit(mini, "reval.yaml", "params: {kind: params, path: params/params.yaml}",
         "params: {kind: params, path: params/params.yaml, derived_from: [data]}")  # fmt: skip
    s0 = mini.snapshot()
    shaft = run(mini, s0, "shaft_check", "D1")
    append(mini, "data/data.csv", "g4,5.0,70.0\n")
    s1 = mini.snapshot()
    fr = _classify(shaft, s0, s1)
    assert fr.cls is F.INVALIDATED
    assert [c.kind for c in fr.relevant_changes] == [K.ROWS_ADDED]


def _waiver_setup(mini: Any) -> tuple[Snapshot, Evidence]:
    s0 = mini.snapshot()
    wp = Producer(
        id="waivers:review", kind=ProducerKind.WAIVER, quantities=("shaft_d",), fidelity=0, cost=0.0,
        code_hash="w" * 64, depends_on=("params#/shaft/d_mm",),
    )  # fmt: skip
    s0 = resnap(s0, producers={**s0.producers, wp.id: wp})
    shaft = run(mini, s0, "shaft_check", "D1")
    w = Evidence.create(
        producer_id=wp.id,
        producer_kind=ProducerKind.WAIVER,
        fidelity=0,
        subject_id="D1",
        result=EvidenceResult(quantity="shaft_d", unit="mm"),
        deps=shaft.deps,
        provenance=Provenance(producer_code_hash=wp.code_hash, snapshot_id=s0.id),
        cost=0.0,
        waiver=Waiver(
            author="a", justification="reviewed", claim_id="C-SHAFT",
            requirement_hash=content_id(s0.requirements["R-SHAFT"]),
        ),
    )  # fmt: skip
    return s0, w


def test_waiver_fresh_until_its_requirement_changes(mini: Any) -> None:
    s0, w = _waiver_setup(mini)
    assert _classify(w, s0, s0).cls is F.FRESH_EXACT
    req = s0.requirements["R-SHAFT"].model_copy(update={"limit": 30.1})
    s1 = resnap(s0, requirements={**s0.requirements, "R-SHAFT": req})
    fr = _classify(w, s0, s1)
    assert fr.cls is F.INVALIDATED and _codes(fr) == {ReasonCode.REQUIREMENT_CHANGED}


def test_waiver_invalidated_when_claim_gone(mini: Any) -> None:
    s0, w = _waiver_setup(mini)
    s1 = resnap(s0, claims={k: v for k, v in s0.claims.items() if k != "C-SHAFT"})
    fr = _classify(w, s0, s1)
    assert fr.cls is F.INVALIDATED and _codes(fr) == {ReasonCode.REQUIREMENT_CHANGED}


def test_missing_producer_invalidates(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    p = pid(mini, "sim_temp")
    s1 = resnap(s0, producers={k: v for k, v in s0.producers.items() if k != p})
    fr = _classify(sim, s0, s1)
    assert fr.cls is F.INVALIDATED and _codes(fr) == {ReasonCode.UNKNOWN_CHANGE}


def test_mismatched_inputs_invalidate(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    edit(mini, "params/params.yaml", "d_mm: 30.00", "d_mm: 30.01")
    s1 = mini.snapshot()
    # A change set for s0 -> s0 passed as if it were s0 -> s1.
    assert classify_evidence(sim, s0, s1, _cs(s0)).cls is F.INVALIDATED
    # Evidence recorded at a different snapshot than `old`.
    assert classify_evidence(sim, s1, s1, diff_snapshots(s1, s1)).cls is F.INVALIDATED


def test_dep_hash_change_without_matching_change_invalidates(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    edit(mini, "params/params.yaml", "gain: 2.0", "gain: 2.1")
    s1 = mini.snapshot()
    fr = classify_evidence(sim, s0, s1, ChangeSet(from_snapshot=s0.id, to_snapshot=s1.id, changes=()))
    assert fr.cls is F.INVALIDATED and _codes(fr) == {ReasonCode.UNKNOWN_CHANGE}


def test_classify_all_missing_old_snapshot(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    items = list(ev.values())
    out = classify_all(items, {}, s0, {})
    assert set(out) == {e.id for e in items}
    for fr in out.values():
        assert fr.cls is F.INVALIDATED and _codes(fr) == {ReasonCode.UNKNOWN_CHANGE}
    ok = classify_all(items, {s0.id: s0}, s0, {s0.id: diff_snapshots(s0, s0)})
    assert {fr.cls for fr in ok.values()} == {F.FRESH_EXACT}
    assert list(ok) == sorted(ok)


def test_unparseable_dependency_never_fresh(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    bad = reev(sim, deps=(*sim.deps, sim.deps[0].model_copy(update={"selector": "params#bad"})))
    assert _classify(bad, s0, s0).cls is F.INVALIDATED
