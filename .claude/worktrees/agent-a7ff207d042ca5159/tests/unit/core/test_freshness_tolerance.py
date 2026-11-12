"""P3-05: tolerance carry-forward (docs/10 §4.3 step 3 fields, D14, D15) and ``carry_forward``."""

from typing import Any

import pytest

from reval.core.diff import diff_snapshots
from reval.core.freshness import FreshnessResult, carry_forward, classify_evidence
from reval.core.selectors import selector_hash
from reval.core.status import AssessInput, assess_claim
from reval.core.verdicts import verdict
from reval.domain.evidence import Dependency, Evidence
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass, ReasonCode, Status, Verdict
from tests.helpers.mini_fresh import edit, reev, run, run_all

F = FreshnessClass


def _classify(e: Evidence, old: Snapshot, new: Snapshot) -> FreshnessResult:
    return classify_evidence(e, old, new, diff_snapshots(old, new))


def _set_scale(mini: Any, value: str) -> Snapshot:
    path = mini.root / "params" / "params.yaml"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(
        "\n".join(f"  scale: {value}" if ln.startswith("  scale:") else ln for ln in lines) + "\n",
        encoding="utf-8",
    )
    snap: Snapshot = mini.snapshot()
    return snap


def test_small_delta_carries_forward_with_exact_inflation(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    s1 = _set_scale(mini, "1.05")
    for sid, sens in (("S1", 40.0), ("S2", 78.0)):
        fr = _classify(ev[("sim_temp", sid)], s0, s1)
        assert fr.cls is F.CARRY_FORWARD and fr.reasons == ()
        assert fr.inflation == pytest.approx(1.5 * sens * 0.05, rel=1e-12)


def test_kappa_applied_exactly_once(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    k1 = reev(sim, tolerances=(sim.tolerances[0].model_copy(update={"safety_factor": 1.0}),))
    fr = _classify(k1, s0, _set_scale(mini, "1.1"))
    assert fr.inflation == pytest.approx(40.0 * 0.1, rel=1e-9)


def test_new_value_outside_valid_range_invalidated(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    fr = _classify(sim, s0, _set_scale(mini, "1.6"))
    assert fr.cls is F.INVALIDATED
    assert {r.code for r in fr.reasons} == {ReasonCode.MISSING_TOLERANCE}


def test_old_value_outside_valid_range_invalidated(mini: Any) -> None:
    s0 = _set_scale(mini, "0.4")
    sim = run(mini, s0, "sim_temp", "S1")
    assert _classify(sim, s0, _set_scale(mini, "0.6")).cls is F.INVALIDATED


def test_boundary_values_are_inside(mini: Any) -> None:
    s0 = _set_scale(mini, "0.5")
    sim = run(mini, s0, "sim_temp", "S1")
    assert _classify(sim, s0, _set_scale(mini, "1.5")).cls is F.CARRY_FORWARD


def test_whole_artifact_dep_with_tolerance_invalidated(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    whole = reev(
        sim, deps=(*sim.deps, Dependency(selector="params", version_hash=selector_hash(s0, "params")))
    )
    fr = _classify(whole, s0, _set_scale(mini, "1.05"))
    assert fr.cls is F.INVALIDATED


def test_non_numeric_change_invalidated(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    assert _classify(sim, s0, _set_scale(mini, "high")).cls is F.INVALIDATED


def test_tolerance_on_other_field_does_not_excuse(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    edit(mini, "params/params.yaml", "gain: 2.0", "gain: 2.01")
    fr = _classify(sim, s0, mini.snapshot())
    assert fr.cls is F.INVALIDATED
    assert {r.code for r in fr.reasons} == {ReasonCode.MISSING_TOLERANCE}


def test_each_change_excused_individually_and_summed(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    gain_tol = sim.tolerances[0].model_copy(
        update={"selector": "params#/sim/gain", "sensitivity": 30.0, "valid_range": (1.0, 3.0)}
    )
    both = reev(sim, tolerances=(*sim.tolerances, gain_tol))
    edit(mini, "params/params.yaml", "gain: 2.0", "gain: 2.2")
    fr = _classify(both, s0, _set_scale(mini, "1.05"))
    assert fr.cls is F.CARRY_FORWARD
    assert fr.inflation == pytest.approx(1.5 * 40.0 * 0.05 + 1.5 * 30.0 * 0.2, rel=1e-9)


def test_tolerance_assumption_change_invalidates(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    edit(mini, "reval.yaml", "bounds: [0.5, 1.5]", "bounds: [0.5, 1.4]")
    fr = _classify(sim, s0, _set_scale(mini, "1.05"))
    assert fr.cls is F.INVALIDATED


def test_wrong_output_unit_raises(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    bad = reev(sim, tolerances=(sim.tolerances[0].model_copy(update={"output_unit": "degC"}),))
    with pytest.raises(ValueError, match="output_unit"):
        _classify(bad, s0, _set_scale(mini, "1.05"))


def test_zero_delta_out_of_scope(mini: Any) -> None:
    # 1.0 -> 1 changes the field hash (float vs int) but not the value: excused, no inflation.
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    fr = _classify(sim, s0, _set_scale(mini, "1"))
    assert (fr.cls, fr.inflation) == (F.FRESH_OUT_OF_SCOPE, 0.0)


def test_carry_forward_without_interval_invalidated(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    no_iv = reev(sim, result=sim.result.model_copy(update={"interval": None}))
    fr = _classify(no_iv, s0, _set_scale(mini, "1.05"))
    assert fr.cls is F.INVALIDATED
    assert {r.code for r in fr.reasons} == {ReasonCode.MISSING_TOLERANCE}


def test_carry_forward_materializes_derived_evidence(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    s1 = _set_scale(mini, "1.05")
    fr = _classify(sim, s0, s1)
    e2 = carry_forward(sim, fr, s1)
    assert e2.derived_from_evidence == sim.id and e2.id != sim.id
    assert e2.provenance.snapshot_id == s1.id
    assert e2.result.interval is not None and sim.result.interval is not None
    assert e2.result.interval.lo == pytest.approx(sim.result.interval.lo - 3.0)
    assert e2.result.interval.hi == pytest.approx(sim.result.interval.hi + 3.0)
    assert e2.result.point == sim.result.point
    assert all(d.version_hash == selector_hash(s1, d.selector) for d in e2.deps)
    assert carry_forward(sim, fr, s1) == e2  # deterministic


def test_carry_forward_rejects_non_carry_results(mini: Any) -> None:
    s0 = mini.snapshot()
    sim = run(mini, s0, "sim_temp", "S1")
    with pytest.raises(ValueError):
        carry_forward(sim, _classify(sim, s0, s0), s0)
    s1 = _set_scale(mini, "1.05")
    fr = _classify(sim, s0, s1)
    other = run(mini, s0, "sim_temp", "S2")
    with pytest.raises(ValueError):
        carry_forward(other, fr, s1)


def test_carried_interval_flips_pass_to_inconclusive_and_claim_goes_stale(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    sim, ml = ev[("sim_temp", "S1")], ev[("predict_temp", "S1")]
    s1 = _set_scale(mini, "1.4")  # inflation = 1.5 * 40 * 0.4 = 24 K: [58, 62] -> [34, 86] straddles 80
    fr_sim, fr_ml = _classify(sim, s0, s1), _classify(ml, s0, s1)
    assert fr_sim.cls is F.CARRY_FORWARD and fr_ml.cls is F.INVALIDATED
    e2 = carry_forward(sim, fr_sim, s1)
    req = s1.requirements["R-TEMP"]
    assert verdict(sim, req)[0] is Verdict.PASS
    assert verdict(e2, req)[0] is Verdict.INCONCLUSIVE
    a = assess_claim(
        s1.claims["C-S1-TEMP"],
        s1,
        [AssessInput(e2, F.CARRY_FORWARD, original=sim), AssessInput(ml, F.INVALIDATED)],
    )
    assert a.status is Status.STALE
