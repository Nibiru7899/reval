"""Optimizer tests with stub model, conformal and drive map (peak = a * torque)."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd
import pytest
from motor.optimizer import energy_J, optimize

from reval.uq.domain import ApplicabilityDomain

A = 0.5  # K per N*m
LIMITS = {"pm_peak_limit_degC": 80.0, "sw_peak_limit_degC": 130.0}
Q = 5.0
BOUNDS = [(0.0, 200.0), (0.0, 4000.0)] * 3
AD_TORQUE_MAX = 120.0


class StubModel:
    targets = ("pm",)
    feature_names: ClassVar[list[str]] = ["torque", "motor_speed"]

    def features(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"pm": A * df["torque"].to_numpy()}, index=df.index)


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


def _run(variant: str, seed: int = 0):
    return optimize(
        variant, StubModel(), StubConformal(), _ad(), StubDriveMap(), LIMITS, BOUNDS,
        seed=seed, popsize=8, maxiter=25,
    )  # fmt: skip


@pytest.fixture(scope="module")
def results():
    return {v: _run(v) for v in ("O1", "O2", "O3")}


def test_o1_respects_point_limit(results) -> None:
    r = results["O1"]
    assert r.pred_peak <= LIMITS["pm_peak_limit_degC"] + 0.5
    assert r.pred_peak > 0.9 * LIMITS["pm_peak_limit_degC"]  # the constraint is active, not vacuous


def test_o2_respects_upper_bound(results) -> None:
    r = results["O2"]
    assert r.upper is not None
    assert r.upper <= LIMITS["pm_peak_limit_degC"] + 0.5
    assert r.upper == pytest.approx(r.pred_peak + Q)
    assert r.pred_peak < results["O1"].pred_peak


def test_o3_is_inside_the_ad_box(results) -> None:
    r = results["O3"]
    assert r.ad_report.inside
    assert float(r.theta[0::2].max()) <= AD_TORQUE_MAX
    assert energy_J(r.theta) > 0


def test_same_seed_same_result() -> None:
    a, b = _run("O2", seed=3), _run("O2", seed=3)
    assert np.array_equal(a.theta, b.theta)
    assert a.subject_params == b.subject_params


def test_subject_params_use_blocks_format(results) -> None:
    p = results["O1"].subject_params
    assert [b[2] for b in p["blocks"]] == [600.0, 900.0, 300.0]
    assert set(p) == {"blocks", "coolant", "ambient"}


def test_unbounded_interval_is_infeasible_for_o2() -> None:
    class Inf(StubConformal):
        def interval(self, target, pred_peak, length_class):
            return None

    r = optimize(
        "O2", StubModel(), Inf(), _ad(), StubDriveMap(), LIMITS, BOUNDS, seed=0, popsize=6, maxiter=5
    )
    assert r.upper is None  # fail closed: never reported as supported


def test_missing_limit_fails_closed() -> None:
    with pytest.raises(ValueError, match="missing limits"):
        optimize("O1", StubModel(), StubConformal(), _ad(), StubDriveMap(), {}, BOUNDS)
