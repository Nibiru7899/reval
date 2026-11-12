"""P5-20: RQ4 2 x 2 optimizer experiment on a stub world (peak = a * torque, truth = a_true * torque)."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from bench.experiments.rq4 import (
    CELLS,
    MIN_RUNS_PER_CELL,
    Rq4Config,
    _run_unchecked,
    run_rq4,
    world_truth_fn,
)
from reval.uq.domain import ApplicabilityDomain

A_MODEL = 0.5
A_TRUE = 0.6  # the plant runs hotter than the model: point optima near the limit are wrong
Q = 5.0
BOUNDS = [(0.0, 200.0), (0.0, 4000.0)] * 3
AD_TORQUE_MAX = 120.0
LIMITS = {"pm_peak_limit_degC": 80.0, "sw_peak_limit_degC": 130.0}


class StubModel:
    targets = ("pm",)
    feature_names: ClassVar[list[str]] = ["torque", "motor_speed"]

    def features(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"pm": A_MODEL * df["torque"].to_numpy()}, index=df.index)


class StubConformal:
    def interval(self, target: str, pred_peak: float, length_class: str) -> tuple[float, float]:
        return pred_peak - Q, pred_peak + Q


class StubDriveMap:
    def to_inputs(self, torque, speed, coolant, ambient) -> pd.DataFrame:
        return pd.DataFrame({"torque": torque, "motor_speed": speed})


def _ad() -> ApplicabilityDomain:
    rng = np.random.default_rng(0)
    x = np.column_stack([rng.uniform(0, AD_TORQUE_MAX, 4000), rng.uniform(0, 4000, 4000)])
    return ApplicabilityDomain(["torque", "motor_speed"], k=5).fit(x[:3000], x[3000:])


def _truth(subject_params, limits) -> bool:
    peak = A_TRUE * max(b[0] for b in subject_params["blocks"])
    return peak > limits["pm_peak_limit_degC"]


@pytest.fixture(scope="module")
def rows() -> pd.DataFrame:
    cfg = Rq4Config(
        seeds=(0, 1, 2), limit_offsets_k=(-5.0, 0.0), base_limits=LIMITS, popsize=8, maxiter=15,
    )  # fmt: skip
    return _run_unchecked(cfg, StubModel(), StubConformal(), _ad(), StubDriveMap(), BOUNDS, _truth)


def test_every_cell_gets_n_rows(rows: pd.DataFrame) -> None:
    assert sorted(rows["cell"].unique()) == sorted(CELLS)
    assert (rows.groupby("cell").size() == 6).all()
    assert {"cell", "accepted", "truth", "run_id"} <= set(rows.columns)


def test_point_acceptance_accepts_every_o1_optimum(rows: pd.DataFrame) -> None:
    o1 = rows[rows["cell"] == "O1/point"]
    assert o1["accepted"].all()
    assert o1["truth"].any()  # the stub plant makes some of those wrong acceptances


def test_gated_acceptance_is_stricter_and_paired(rows: pd.DataFrame) -> None:
    p = rows[rows["cell"] == "O1/point"].set_index("run_id")
    g = rows[rows["cell"] == "O1/gated"].set_index("run_id")
    assert list(p.index) == list(g.index)
    assert (g["accepted"] <= p["accepted"]).all()
    wrong_p = (p["accepted"] & p["truth"]).sum()
    wrong_g = (g["accepted"] & g["truth"]).sum()
    assert wrong_g < wrong_p


def test_minimum_runs_enforced() -> None:
    small = Rq4Config(seeds=(0,), limit_offsets_k=(0.0,), base_limits=LIMITS)
    with pytest.raises(ValueError, match="MIN_RUNS_PER_CELL"):
        run_rq4(small, StubModel(), StubConformal(), _ad(), StubDriveMap(), BOUNDS, _truth)
    assert MIN_RUNS_PER_CELL == 50


def test_deterministic_for_same_seed() -> None:
    cfg = Rq4Config(seeds=(4,), limit_offsets_k=(0.0,), base_limits=LIMITS, popsize=8, maxiter=10)
    a = _run_unchecked(cfg, StubModel(), StubConformal(), _ad(), StubDriveMap(), BOUNDS, _truth)
    b = _run_unchecked(cfg, StubModel(), StubConformal(), _ad(), StubDriveMap(), BOUNDS, _truth)
    pd.testing.assert_frame_equal(a, b)


def test_world_truth_fn_uses_world_peak() -> None:
    class StubWorld:
        def simulate(self, x: pd.DataFrame, physical: object) -> pd.DataFrame:
            return pd.DataFrame({"pm": 0.6 * x["torque"].to_numpy()})

    fn = world_truth_fn(StubWorld(), None, StubDriveMap())  # type: ignore[arg-type]
    params = {"blocks": [[100.0, 1000.0, 10.0]], "coolant": 27.0, "ambient": 24.0}  # peak 60
    assert fn(params, {"pm_peak_limit_degC": 50.0}) is True
    assert fn(params, {"pm_peak_limit_degC": 60.0}) is False  # hitting the limit satisfies it


def test_rq4_summary_counts_wrong_acceptances() -> None:
    from bench.experiments.rq4 import rq4_summary

    df = pd.DataFrame(
        {
            "cell": ["O1/point"] * 3,
            "accepted": [True, True, False],
            "truth": [True, False, True],
        }
    )
    assert rq4_summary(df) == "O1/point: n=3 accepted=2 wrong_accept=1"


def test_main_without_workspace_only_reports_the_design(capsys: pytest.CaptureFixture[str]) -> None:
    from bench.experiments.rq4 import main

    main([])
    out = capsys.readouterr().out
    assert "4 cells x 54 runs" in out and "--workspace" in out
