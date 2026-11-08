"""Ablation switches A1-A3, A7 reach core as arguments (docs/10 settings.py); defaults are the full method."""

from typing import Any

import pytest

from reval.core.diff import diff_snapshots
from reval.core.freshness import FreshnessResult, classify_all
from reval.domain.evidence import Evidence, Scope
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass
from tests.helpers.mini_fresh import append, edit, reev, run_all

F = FreshnessClass


def _all(
    ev: dict[tuple[str, str], Evidence], s0: Snapshot, s1: Snapshot, **kw: Any
) -> dict[tuple[str, str], FreshnessResult]:
    out = classify_all(list(ev.values()), {s0.id: s0}, s1, {s0.id: diff_snapshots(s0, s1)}, **kw)
    return {k: out[e.id] for k, e in ev.items()}


def _scale_edit(mini: Any) -> tuple[dict[tuple[str, str], Evidence], Snapshot, Snapshot]:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    edit(mini, "params/params.yaml", "scale: 1.0", "scale: 1.02")
    return ev, s0, mini.snapshot()


def test_defaults_identical_to_no_settings(mini: Any) -> None:
    ev, s0, s1 = _scale_edit(mini)
    assert _all(ev, s0, s1) == _all(ev, s0, s1, settings=DEFAULT_SETTINGS)
    assert _all(ev, s0, s1) == _all(ev, s0, s1, settings=ReValSettings())


def test_a1_whole_artifact_deps_invalidate_unrelated_field_edit(mini: Any) -> None:
    ev, s0, s1 = _scale_edit(mini)
    assert _all(ev, s0, s1)[("shaft_check", "D1")].cls is F.FRESH_EXACT
    off = _all(ev, s0, s1, settings=ReValSettings(field_level_selectors=False))
    assert off[("shaft_check", "D1")].cls is F.INVALIDATED
    assert (
        off[("sim_temp", "S1")].cls is F.INVALIDATED
    )  # a whole-artifact dep is never excused by a tolerance


def test_a2_no_carry_forward(mini: Any) -> None:
    ev, s0, s1 = _scale_edit(mini)
    assert _all(ev, s0, s1)[("sim_temp", "S1")].cls is F.CARRY_FORWARD
    off = _all(ev, s0, s1, settings=ReValSettings(tolerance_carry_forward=False))
    assert off[("sim_temp", "S1")].cls is F.INVALIDATED
    assert off[("shaft_check", "D1")].cls is F.FRESH_EXACT  # exact reuse is unaffected


def test_a7_kappa_override_replaces_safety_factor(mini: Any) -> None:
    ev, s0, s1 = _scale_edit(mini)
    fr = _all(ev, s0, s1, settings=ReValSettings(kappa_override=3.0))
    assert fr[("sim_temp", "S1")].inflation == pytest.approx(3.0 * 40.0 * 0.02)


def test_a7_kappa_override_is_validated() -> None:
    for bad in (0.0, 0.5, -1.0):
        with pytest.raises(ValueError):
            ReValSettings(kappa_override=bad)


def test_a3_no_scope_excuse(mini: Any) -> None:
    s0 = mini.snapshot()
    ev = run_all(mini, s0)
    e = ev[("measure_temp", "S1")]
    ev[("measure_temp", "S1")] = reev(
        e, scope=Scope(box={**e.scope.box, "x": (0.0, 1.9)}, assumption_ids=e.scope.assumption_ids)
    )
    append(mini, "data/data.csv", "g4,5.0,70.0\ng4,6.0,80.0\n")
    s1 = mini.snapshot()
    assert _all(ev, s0, s1)[("measure_temp", "S1")].cls is F.FRESH_OUT_OF_SCOPE
    off = _all(ev, s0, s1, settings=ReValSettings(scope_freshness=False))
    assert off[("measure_temp", "S1")].cls is F.INVALIDATED
