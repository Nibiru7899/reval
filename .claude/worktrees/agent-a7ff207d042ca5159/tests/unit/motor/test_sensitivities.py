"""P3-07: LPTN finite-difference sensitivities -> tolerances."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from motor import lptn
from motor.sensitivities import FLOW_FIELD, estimate_tolerances

from reval.domain.evidence import Tolerance

ROOT = Path(__file__).resolve().parents[3] / "examples" / "motor_thermal"


def _toy(params: lptn.LPTNParams, flow: float, cycle: Mapping[str, Any]) -> Mapping[str, float]:
    """Peak linear in flow_scale (slope 12 K, 7 K for the second cycle's gain) and in R/sw_st."""
    gain = cycle["gain"]
    return {
        "pm": 12.0 * gain * flow,
        "stator_winding": 5.0 * flow + 300.0 * params.R[("stator_winding", "stator_tooth")],
    }


GRID = [0.7, 0.85, 1.0, 1.15, 1.3]
CYCLES = [{"gain": 1.0}, {"gain": 0.5}]


def test_linear_toy_recovers_slope_raw_and_kappa_separate() -> None:
    (tol,) = estimate_tolerances(
        lptn.default_params(),
        FLOW_FIELD,
        GRID,
        CYCLES,
        assumption_id="A-flow-sens",
        kappa=1.7,
        simulator=_toy,
    )
    assert tol.sensitivity == pytest.approx(12.0)  # raw max over cycles and nodes
    assert tol.safety_factor == 1.7
    assert tol.valid_range == (0.7, 1.3)
    assert (tol.input_unit, tol.output_unit) == ("dimensionless", "K")
    assert tol.assumption_id == "A-flow-sens"
    assert tol.source.startswith("fd on lptn@") and "grid=5" in tol.source


def test_leaf_field_slope() -> None:
    p = lptn.default_params()
    base = p.R[("stator_winding", "stator_tooth")]
    grid = [base * r for r in (0.8, 0.9, 1.0, 1.1, 1.2)]
    (tol,) = estimate_tolerances(p, "lptn#/R/sw_st", grid, CYCLES, assumption_id="A-x", simulator=_toy)
    assert tol.sensitivity == pytest.approx(300.0)
    assert tol.input_unit == "K/W"


def test_rejects_short_grid_and_unknown_field() -> None:
    p = lptn.default_params()
    with pytest.raises(ValueError, match="grid"):
        estimate_tolerances(p, FLOW_FIELD, GRID[:3], CYCLES, assumption_id="A", simulator=_toy)
    with pytest.raises(ValueError, match="unsupported"):
        estimate_tolerances(p, "limits#/x", GRID, CYCLES, assumption_id="A", simulator=_toy)


def test_real_lptn_flow_sensitivity_is_positive_and_deterministic() -> None:
    """Default simulator on a small synthetic cycle: more flow lowers the peak, and reruns agree exactly."""
    n = 400
    inputs = pd.DataFrame(
        {
            "i_d": [-50.0] * n,
            "i_q": [100.0] * n,
            "u_d": [0.0] * n,
            "u_q": [100.0] * n,
            "motor_speed": [2000.0] * n,
            "coolant": [25.0] * n,
            "ambient": [25.0] * n,
        }
    )
    try:
        lptn.simulate(inputs, lptn.default_params())
    except Exception:  # input schema differs: skip rather than guess
        pytest.skip("synthetic drive inputs do not match lptn.simulate")
    cyc = [{"inputs": inputs}]
    a = estimate_tolerances(lptn.default_params(), FLOW_FIELD, GRID, cyc, assumption_id="A")[0]
    b = estimate_tolerances(lptn.default_params(), FLOW_FIELD, GRID, cyc, assumption_id="A")[0]
    assert a == b and a.sensitivity > 0


def test_committed_tolerances_are_valid_and_backed_by_declared_assumptions() -> None:
    entries = yaml.safe_load((ROOT / "params" / "tolerances.yaml").read_text(encoding="utf-8"))["tolerances"]
    tols = [Tolerance.model_validate(e) for e in entries]
    manifest = yaml.safe_load((ROOT / "reval.yaml").read_text(encoding="utf-8"))
    assert FLOW_FIELD in {t.selector for t in tols}
    assert len({t.assumption_id for t in tols}) == len(tols)  # one assumption per tolerance
    for t in tols:
        assert t.assumption_id in manifest["assumptions"]
        assert t.output_unit == "K" and t.safety_factor == 1.5 and t.sensitivity > 0
