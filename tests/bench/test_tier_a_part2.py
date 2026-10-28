"""P5-04: T6, T10, T11 appliers on the mini project."""

from pathlib import Path

import pytest

from bench.scenarios.tier_a import change_bounds, patch_function
from tests.bench._impact import impact, scenarios


def test_change_bounds_moves_one_end_by_fraction_of_width() -> None:
    assert change_bounds([10, 100], "upper", True, 0.2) == [10.0, 82.0]
    assert change_bounds([10, 100], "lower", False, 0.1) == [1.0, 100.0]
    with pytest.raises(ValueError):
        change_bounds([0, 1], "upper", True, 1.5)


def test_t6_changes_only_the_assumption_and_spares_the_shaft(tmp_path: Path) -> None:
    sc = scenarios("T6", n=1)[0]
    change, rep = impact(tmp_path, sc)
    assert change.declared == ["reval.yaml"]
    assert change.notes["new"] != change.notes["old"]
    assert "C-SHAFT" not in rep.affected_claims
    assert "C-S1-TEMP" in rep.affected_claims  # its ML evidence assumes A-ambient and is scoped by it


@pytest.mark.parametrize("i", range(4))
def test_t10_affects_only_the_shaft_claim_or_nothing(tmp_path: Path, i: int) -> None:
    sc = scenarios("T10", n=4)[i]
    change, rep = impact(tmp_path, sc)
    assert set(rep.affected_claims) <= {"C-SHAFT"}
    assert change.declared in (["README.md"], ["params/params.yaml"])
    if sc.params["flavor"] == "shaft":
        assert rep.affected_claims == ("C-SHAFT",)


def test_t10_generator_covers_both_flavors() -> None:
    assert {s.params["flavor"] for s in scenarios("T10", n=12)} == {"readme", "shaft"}


@pytest.mark.parametrize("flavor", ["refactor", "fix"])
def test_t11_both_flavors_invalidate_the_patched_producer(tmp_path: Path, flavor: str) -> None:
    sc = scenarios("T11", n=1)[0].model_copy(update={"params": {"flavor": flavor}})
    change, rep = impact(tmp_path, sc)
    assert change.declared == ["mini/producers.py"]
    # fail closed: even the behavior-preserving rename changes the code hash, so sim_temp's evidence is stale
    assert "C-S1-TEMP" in rep.affected_claims
    # (the code hash covers the whole producers module, so unpatched producers in it go stale too)


def test_patch_function_is_scoped_and_refuses_a_noop() -> None:
    src = "def a(x):\n    return x\n\n\ndef b(x):\n    return x\n"
    out = patch_function(src, "a", lambda body: body.replace("x", "y"))
    assert out == "def a(y):\n    return y\n\n\ndef b(x):\n    return x\n"
    with pytest.raises(ValueError):
        patch_function(src, "a", lambda body: body)
    with pytest.raises(ValueError):
        patch_function(src, "missing", lambda body: body)
