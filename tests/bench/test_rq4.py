"""P5-20: RQ4 2 x 2 optimizer experiment on a stub world (peak = a * torque, truth = a_true * torque)."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from bench.experiments.rq4 import CELLS, Rq4Config, run_rq4
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
        min_runs_per_cell=1,
    )  # fmt: skip
    return run_rq4(cfg, StubModel(), StubConformal(), _ad(), StubDriveMap(), BOUNDS, _truth)


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
    with pytest.raises(ValueError, match="min_runs_per_cell"):
        Rq4Config(seeds=(0,), limit_offsets_k=(0.0,), base_limits=LIMITS, min_runs_per_cell=50)
