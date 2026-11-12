import numpy as np
import pandas as pd
import pytest
from motor import lptn
from motor.lptn import NODES, LPTNParams


def _frame(n: int, *, i: float = 0.0, w: float = 0.0, coolant: float = 25.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "i_d": np.zeros(n),
            "i_q": np.full(n, i),
            "u_d": np.zeros(n),
            "u_q": np.zeros(n),
            "motor_speed": np.full(n, w),
            "coolant": np.full(n, coolant),
            "ambient": np.full(n, coolant),
        }
    )


def _params() -> LPTNParams:
    return lptn.default_params()


def test_zero_losses_constant_temperatures():
    p = _params()
    out = lptn.simulate(_frame(500), p, theta0=dict.fromkeys(NODES, 25.0))
    assert list(out.columns) == list(NODES)
    assert np.allclose(out.to_numpy(), 25.0)


def test_default_theta0_is_coolant():
    out = lptn.simulate(_frame(10, coolant=40.0), _params())
    assert np.allclose(out.iloc[0].to_numpy(), 40.0)


def test_step_loss_rises_monotonically_to_analytic_steady_state():
    base = _params()
    # Isolate the winding: huge resistances everywhere except SW-ambient, so it is a 1-node system.
    big = 1.0e6
    p = LPTNParams(
        C={**base.C, "stator_winding": 200.0},
        R={pair: big for pair in base.R} | {("stator_winding", "ambient"): 0.1},
        k_cu=0.01,
        alpha_cu=0.0,
        k_fe1=0.0,
        k_fe2=0.0,
        k_pm=0.0,
    )
    i = 100.0
    n = 4000  # 2000 s >> tau = 20 s
    out = lptn.simulate(_frame(n, i=i, coolant=25.0), p, theta0=dict.fromkeys(NODES, 25.0))
    sw = out["stator_winding"].to_numpy()
    assert np.all(np.diff(sw) >= 0)
    analytic = 25.0 + 0.01 * i**2 * 0.1
    assert sw[-1] == pytest.approx(analytic, rel=0.01)


def test_lower_flow_raises_steady_state():
    p = _params()
    frame = _frame(40000, i=200.0, w=3000.0, coolant=30.0)
    hot = lptn.simulate(frame, p, flow_scale=0.5)
    ref = lptn.simulate(frame, p, flow_scale=1.0)
    assert (hot.iloc[-1] > ref.iloc[-1]).all()
    assert lptn.r_coolant(0.04, 0.5) == pytest.approx(0.04 * 0.5**-0.8)


def test_stability_guard_raises():
    with pytest.raises(ValueError, match="stability"):
        lptn.simulate(_frame(10), _params(), dt=1.0e4)


def test_losses_shapes_and_signs():
    p = _params()
    out = lptn.losses(
        np.array([0.0, 100.0]), np.array([0.0, 50.0]), np.array([0.0, -2000.0]), np.array([20.0, 80.0]), p
    )
    assert set(out) == set(NODES)
    assert out["stator_winding"][0] == 0.0
    assert all((v >= 0).all() for v in out.values())


def test_params_round_trip(tmp_path):
    p = _params()
    path = tmp_path / "lptn.yaml"
    lptn.dump_params(p, path)
    assert "sw_st:" in path.read_text()
    assert lptn.load_params(path) == p
