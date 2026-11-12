"""Tier B world model: structure, physics sanity, R7 calibration guard, and (data) test-set MSE."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from motor import lptn
from motor.splits import Splits, load_splits, split_frame

from bench.world import PhysicalParams, World, default_world_params
from bench.world.calibrate import calibrate_world, evaluate_world_mse, get_world
from bench.world.model import FIT_NAMES, NODES

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "motor_thermal"
CACHE = Path(__file__).resolve().parents[2] / "bench" / "cache" / "world"


def _traj(n: int = 4000, w: float = 3000.0, pid: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "profile_id": pid,
            "t": np.arange(n) * 0.5,
            "i_d": -80.0,
            "i_q": 150.0,
            "u_d": -20.0,
            "u_q": 90.0,
            "motor_speed": w,
            "coolant": 30.0,
            "ambient": 25.0,
        }
    )


def test_structure_differs_from_design_lptn() -> None:
    assert len(NODES) >= 6 and len(NODES) > len(lptn.NODES)
    design_names = {f"/C/{k}" for k in lptn.C_KEYS.values()} | {f"/R/{k}" for k in lptn.R_KEYS.values()}
    design_names |= {f"/loss/{k}" for k in lptn.LOSS_KEYS} | set(lptn.NODES)
    assert design_names.isdisjoint(FIT_NAMES)
    assert design_names.isdisjoint(NODES) or set(NODES) != set(lptn.NODES)


def test_simulate_shape_determinism_and_heating() -> None:
    world = World(default_world_params())
    tr = _traj()
    a, b = world.simulate(tr), world.simulate(tr)
    pd.testing.assert_frame_equal(a, b)
    assert list(a.columns) == ["pm", "stator_yoke", "stator_tooth", "stator_winding"]
    assert len(a) == len(tr) and np.isfinite(a.to_numpy()).all()
    assert a["stator_winding"].iloc[-1] > a["stator_winding"].iloc[0]


def test_physical_params_move_temperatures_the_right_way() -> None:
    world = World(default_world_params())
    tr = _traj()
    base = world.simulate(tr)["stator_yoke"].iloc[-1]
    assert world.simulate(tr, PhysicalParams(R_ic_scale=1.5))["stator_yoke"].iloc[-1] > base
    assert world.simulate(tr, PhysicalParams(coolant_flow_scale=0.6))["stator_yoke"].iloc[-1] > base
    assert world.simulate(tr, PhysicalParams(coolant_flow_scale=1.4))["stator_yoke"].iloc[-1] < base
    # the sensor offset is a measurement effect only, not a state change
    assert world.simulate(tr, PhysicalParams(sensor_offset=2.0)).equals(world.simulate(tr))


def test_measure_noise_offset_and_crn_determinism() -> None:
    world = World(default_world_params())
    tr = _traj(1000)
    clean = world.simulate(tr)
    m1 = world.measure(tr, PhysicalParams(sensor_offset=2.0), np.random.default_rng(7))
    m2 = world.measure(tr, PhysicalParams(sensor_offset=2.0), np.random.default_rng(7))
    pd.testing.assert_frame_equal(m1, m2)
    d = m1 - clean
    assert abs(d["pm"].mean() - 2.0) < 0.1
    assert abs(d["stator_yoke"].mean()) < 0.1
    assert 0.3 < d["stator_yoke"].std() < 0.7  # sigma_sensor = 0.5 K


def test_model_form_error_is_a_smooth_function_of_speed() -> None:
    p = default_world_params()
    no_err = World(type(p)(p.values, 0.0, p.sigma_sensor_k))
    with_err = World(p)
    gap = {
        w: with_err.simulate(_traj(w=w)).iloc[-1] - no_err.simulate(_traj(w=w)).iloc[-1]
        for w in (0.0, 3000.0)
    }
    assert gap[0.0].abs().max() < 0.1  # bump is ~0 away from 3 krpm
    assert gap[3000.0]["pm"] > 10 * gap[0.0]["pm"] and gap[3000.0]["pm"] > 0.5


def test_calibration_uses_only_train_and_reserve() -> None:
    frames = []
    for pid in range(1, 9):
        f = _traj(1200, w=500.0 * pid, pid=pid)
        for n, off in (("pm", 5), ("stator_yoke", 1), ("stator_tooth", 3), ("stator_winding", 4)):
            f[n] = 30.0 + off
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    sp = Splits(train=(1, 2, 3), calib=(4, 5), test=(6, 7), reserve=(8,))
    _, info = calibrate_world(df, sp, max_profiles=10, max_blocks=40, max_nfev=1)
    assert set(info["profiles"]) <= {1, 2, 3, 8}
    assert info["fit_splits"] == ["train", "reserve"]


@pytest.mark.data
@pytest.mark.slow
def test_world_mse_on_test_profiles_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    parquet = EXAMPLE / "data" / "processed" / "measures.parquet"
    if not parquet.exists():
        pytest.skip("motor data not downloaded")
    df = pd.read_parquet(parquet)
    splits = load_splits(EXAMPLE / "splits.yaml")
    world = get_world(CACHE, df, splits)  # calibrates once (about 5 min), then reads the cache
    test = split_frame(df, splits, "test")
    mse = evaluate_world_mse(world, test)
    with capsys.disabled():
        print(f"\nworld test MSE (K^2) per node: {mse}")
    assert all(np.isfinite(v) for v in mse.values())
