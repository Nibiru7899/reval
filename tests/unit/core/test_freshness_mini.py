"""Freshness end to end on the mini project: real edits -> build_snapshot -> diff -> classify_all."""

from typing import Any

import pytest

from reval.core.diff import diff_snapshots
from reval.core.freshness import FreshnessResult, classify_all
from reval.domain.evidence import Evidence, Scope
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass, ReasonCode
from tests.helpers.mini_fresh import append, edit, reev, run_all

F = FreshnessClass


def _all(
    ev: dict[tuple[str, str], Evidence], s0: Snapshot, s1: Snapshot
) -> dict[tuple[str, str], FreshnessResult]:
    out = classify_all(list(ev.values()), {s0.id: s0}, s1, {s0.id: diff_snapshots(s0, s1)})
    return {k: out[e.id] for k, e in ev.items()}


def test_load_scale_within_tolerance(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    edit(mini, "params/params.yaml", "scale: 1.0", "scale: 1.02")
    fr = _all(ev, s0, mini.snapshot())
    assert fr[("sim_temp", "S1")].cls is F.CARRY_FORWARD
    assert fr[("sim_temp", "S1")].inflation == pytest.approx(1.5 * 40.0 * 0.02)
    assert fr[("sim_temp", "S2")].cls is F.CARRY_FORWARD
    assert fr[("sim_temp", "S2")].inflation == pytest.approx(1.5 * 78.0 * 0.02)
    for sid in ("S1", "S2"):
        ml = fr[("predict_temp", sid)]
        assert ml.cls is F.INVALIDATED
        assert {r.code for r in ml.reasons} == {ReasonCode.MISSING_TOLERANCE}
    assert fr[("shaft_check", "D1")].cls is F.FRESH_EXACT
    assert fr[("measure_temp", "S1")].cls is F.FRESH_EXACT


def test_shaft_edit_invalidates_only_shaft_evidence(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    edit(mini, "params/params.yaml", "d_mm: 30.00", "d_mm: 30.04")
    fr = _all(ev, s0, mini.snapshot())
    assert {k for k, r in fr.items() if r.cls is not F.FRESH_EXACT} == {("shaft_check", "D1")}
    assert fr[("shaft_check", "D1")].cls is F.INVALIDATED


def test_rows_outside_scope_excuse_column_deps_but_not_derived_surrogate(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    box = {"x": (0.0, 1.9)}
    # Give the data-reading items a scope box over x (the mini producers declare none on data columns).
    for key in (("measure_temp", "S1"), ("predict_temp", "S1")):
        e = ev[key]
        ev[key] = reev(e, scope=Scope(box={**e.scope.box, **box}, assumption_ids=e.scope.assumption_ids))
    append(mini, "data/data.csv", "g4,5.0,70.0\ng4,6.0,80.0\n")  # a new group, x outside the box
    fr = _all(ev, s0, mini.snapshot())
    assert fr[("measure_temp", "S1")].cls is F.FRESH_OUT_OF_SCOPE  # data[temp] only: excused
    assert fr[("predict_temp", "S1")].cls is F.INVALIDATED  # also depends on surrogate <- data (D3)
    assert fr[("predict_temp", "S2")].cls is F.INVALIDATED
    for key in (("sim_temp", "S1"), ("sim_temp", "S2"), ("shaft_check", "D1")):
        assert fr[key].cls is F.FRESH_EXACT
