"""Tier B base snapshots on a tiny synthetic project (no real data)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from motor.models import load
from motor.splits import load_splits, split_frame

from bench.world import PhysicalParams, World, default_world_params
from bench.world.base import MEASUREMENTS_FILE, build_tier_b_base, crn_rng, world_trajectories

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "motor_thermal"
SPLITS = {"train": [1, 2, 3, 4], "calib": [5, 6], "test": [7, 8], "reserve": [9]}


def _synthetic(n: int = 8000) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    frames = []
    for pid in range(1, 10):
        steps = n // 400
        w = np.repeat(rng.uniform(300, 4500, steps), 400)
        i_q = np.repeat(rng.uniform(-200, 250, steps), 400)
        f = pd.DataFrame(
            {
                "profile_id": pid,
                "t": np.arange(n) * 0.5,
                "motor_speed": w[:n],
                "i_q": i_q[:n],
                "i_d": -0.3 * np.abs(i_q[:n]),
                "u_q": 0.02 * w[:n] + 0.1 * i_q[:n],
                "u_d": -0.05 * np.abs(i_q[:n]),
                "torque": 0.2 * i_q[:n],
                "coolant": 28.0,
                "ambient": 23.0,
                "pm": 30.0,
                "stator_yoke": 29.0,
                "stator_tooth": 30.0,
                "stator_winding": 31.0,
            }
        )
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "data" / "processed").mkdir(parents=True)
    shutil.copytree(EXAMPLE / "motor", root / "motor", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(EXAMPLE / "scripts", root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "params").mkdir()
    shutil.copy(EXAMPLE / "params" / "lptn.yaml", root / "params" / "lptn.yaml")
    (root / "splits.yaml").write_text(yaml.safe_dump({**SPLITS, "published_test_ids": [], "seed": 0}))
    subjects = {
        "DC-R01": {
            "kind": "duty_cycle",
            "generator": "motor.cycles:recorded",
            "params": {"profile_id": 7, "start_s": 100.0, "duration_s": 600.0},
        },
        "DC-P01": {"kind": "duty_cycle", "generator": "motor.cycles:blocks", "params": {}},
    }
    (root / "subjects.yaml").write_text(yaml.safe_dump(subjects))
    _synthetic().to_parquet(root / "data" / "processed" / "measures.parquet", index=False)
    return root


def _mse(model_path: Path, df: pd.DataFrame) -> float:
    model = load(model_path)
    pred = model.predict(df)
    return float(np.mean((df["pm"].to_numpy(float) - pred["pm"].to_numpy(float)) ** 2))


@pytest.mark.slow
def test_retrained_model_fits_world_better_and_table_is_deterministic(project: Path) -> None:
    base = default_world_params()
    other = World(type(base)({**base.values, "G_hs_cool": base.values["G_hs_cool"] * 0.4}))
    target = World(base)
    phys = PhysicalParams()
    kw = {"models": ("ridge",), "write_lock": False, "lptn_args": ("--max-profiles", "3", "--max-nfev", "2")}

    build_tier_b_base(project, other, phys, seed=1, **kw)
    original = project / "models" / "tpm_original.joblib"
    shutil.copy(project / "models" / "tpm_ridge.joblib", original)

    build_tier_b_base(project, target, phys, seed=1, **kw)
    table1 = (project / MEASUREMENTS_FILE).read_text(encoding="utf-8")
    world_df = pd.read_parquet(project / "data" / "processed" / "measures.parquet")
    splits = load_splits(project / "splits.yaml")
    test = split_frame(world_df, splits, "test")
    retrained = _mse(project / "models" / "tpm_ridge.joblib", test)
    assert retrained < _mse(original, test)

    # the table lists recorded-cycle subjects only, is undeclared, and follows the CRN seed
    table = json.loads(table1)
    assert list(table) == ["DC-R01"] and set(table["DC-R01"]) == {"pm_peak", "sw_peak"}
    assert crn_rng(1, "DC-R01").bit_generator.state == crn_rng(1, "DC-R01").bit_generator.state
    build_tier_b_base(project, target, phys, seed=1, **kw)
    assert (project / MEASUREMENTS_FILE).read_text(encoding="utf-8") == table1
    build_tier_b_base(project, target, phys, seed=2, **kw)
    assert (project / MEASUREMENTS_FILE).read_text(encoding="utf-8") != table1


def test_world_trajectories_replace_temperatures() -> None:
    world = World(default_world_params())
    df = _synthetic(2000)
    out = world_trajectories(world, df, PhysicalParams())
    assert out["pm"].iloc[1] != df["pm"].iloc[1] and (out["pm"].iloc[0] == df["pm"].iloc[0])
    assert (out.drop(columns=["pm", "stator_yoke", "stator_tooth", "stator_winding"])).equals(
        df.drop(columns=["pm", "stator_yoke", "stator_tooth", "stator_winding"])
    )
    # same answer as the single-profile simulate
    g = df[df["profile_id"] == 3].reset_index(drop=True)
    single = world.simulate(g)
    np.testing.assert_allclose(
        out[out["profile_id"] == 3]["pm"].to_numpy(), single["pm"].to_numpy(), rtol=1e-9
    )


def test_crn_rng_is_deterministic_and_subject_specific() -> None:
    a = crn_rng(5, "DC-R01").normal(size=3)
    assert np.array_equal(a, crn_rng(5, "DC-R01").normal(size=3))
    assert not np.array_equal(a, crn_rng(5, "DC-R02").normal(size=3))
