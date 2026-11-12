"""P5-07: B0 rerun-all oracle on the mini project, with hand-labelled cases."""

from pathlib import Path

import pytest

from bench.harness.cache import ProducerResultCache
from bench.oracles.evidence import (
    ClaimOutcome,
    epsilon_from_halfwidths,
    run_b0,
    truly_affected,
)
from reval.domain.status import Status
from tests.bench._mini import copy_mini, edit, open_project

EPS = {"temp_peak": 0.5, "shaft_d": 0.001}


def _b0(root: Path, cache: ProducerResultCache):  # type: ignore[no-untyped-def]
    proj = open_project(root)
    snap = proj.snapshot()
    return run_b0(proj, snap, cache)


def test_epsilon_is_tenth_of_median_halfwidth() -> None:
    assert epsilon_from_halfwidths({"pm_peak": [1.0, 3.0, 5.0]}) == {"pm_peak": pytest.approx(0.3)}


def test_hand_labelled_outcomes() -> None:
    s = Status.SUPPORTED
    base = {"c1": ClaimOutcome(s, "temp_peak", {"sim|S1|temp_peak": 50.0, "meas|S1|temp_peak": 60.0})}
    cases = {
        "identical": ({"sim|S1|temp_peak": 50.0, "meas|S1|temp_peak": 60.0}, s, False),
        "within eps": ({"sim|S1|temp_peak": 50.4, "meas|S1|temp_peak": 60.0}, s, False),
        # only the clause that is NOT the one satisfying the claim moves
        "unused clause moved": ({"sim|S1|temp_peak": 50.0, "meas|S1|temp_peak": 61.0}, s, True),
        "evidence vanished": ({"sim|S1|temp_peak": 50.0}, s, True),
        "status flipped": ({"sim|S1|temp_peak": 50.0, "meas|S1|temp_peak": 60.0}, Status.STALE, True),
    }
    for name, (values, status, expected) in cases.items():
        got = truly_affected(base, {"c1": ClaimOutcome(status, "temp_peak", values)}, EPS)
        assert got == {"c1": expected}, name


def test_missing_epsilon_is_an_error() -> None:
    o = {"c": ClaimOutcome(Status.SUPPORTED, "unknown_q", {"a": 1.0})}
    with pytest.raises(KeyError):
        truly_affected(o, o, EPS)


def test_unchanged_project_has_no_affected_claims_and_cache_hits(tmp_path: Path) -> None:
    root = copy_mini(tmp_path)
    cache = ProducerResultCache(tmp_path / "cache")
    r1 = _b0(root, cache)
    assert cache.misses > 0 and cache.hits == 0
    misses = cache.misses
    r2 = _b0(root, cache)
    assert cache.misses == misses and cache.hits == len(r2.runs)  # every run is a byte-identical hit
    assert [e.id for e in r1.evidence] == [e.id for e in r2.evidence]
    assert not any(truly_affected(r1.outcomes, r2.outcomes, EPS).values())
    assert r1.cost == pytest.approx(18.5)  # S1: 1+3+10, S2: 1+3, D1: 0.5


def test_shaft_change_affects_only_shaft_claim(tmp_path: Path) -> None:
    root = copy_mini(tmp_path)
    cache = ProducerResultCache(tmp_path / "cache")
    before = _b0(root, cache)
    edit(root, "params/params.yaml", "d_mm: 30.00", "d_mm: 30.04")
    after = _b0(root, cache)
    labels = truly_affected(before.outcomes, after.outcomes, EPS)
    assert [c for c, v in labels.items() if v] == ["C-SHAFT"]


def test_gain_change_reaches_claims_through_physics_value(tmp_path: Path) -> None:
    root = copy_mini(tmp_path)
    cache = ProducerResultCache(tmp_path / "cache")
    before = _b0(root, cache)
    edit(root, "params/params.yaml", "gain: 2.0", "gain: 2.2")
    after = _b0(root, cache)
    labels = truly_affected(before.outcomes, after.outcomes, EPS)
    assert not labels["C-SHAFT"]
    assert labels["C-S1-TEMP"] and labels["C-S2-TEMP"]
