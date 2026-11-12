from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from motor.models import TARGETS, TrajectoryModel, evaluate, load, peaks, save
from motor.splits import load_splits, split_frame

DATA = Path("examples/motor_thermal/data/processed/measures.parquet")
SPLITS = Path("examples/motor_thermal/splits.yaml")


def test_ridge_fits_linear_target(synthetic_measures):
    df = synthetic_measures(n_profiles=2, n_rows=400)
    # Target linear in a (scaled) input feature, so ridge recovers it almost exactly.
    df["pm"] = 3.0 + 0.02 * df["i_q"] - 0.01 * df["coolant"]
    df["stator_winding"] = 1.0 + 0.005 * df["motor_speed"]
    m = TrajectoryModel("ridge", alpha=1e-6).fit(df)
    pred = m.predict(df)
    assert list(pred.columns) == list(TARGETS)
    for t in TARGETS:
        assert float(np.mean((pred[t] - df[t]) ** 2)) < 1e-3


def test_peaks_on_ramp_returns_window_ends_and_drops_partial():
    y = pd.Series(np.arange(25, dtype=float))
    pid = pd.Series([1] * 12 + [2] * 13)
    out = peaks(y, pid, 5)
    # profile 1: windows [0-4],[5-9] (rows 10-11 dropped); profile 2: [12-16],[17-21] (22-24 dropped)
    assert out.tolist() == [4.0, 9.0, 16.0, 21.0]


def test_save_load_roundtrip(synthetic_measures, tmp_path):
    df = synthetic_measures(n_profiles=2, n_rows=300)
    m = TrajectoryModel("hgb", max_iter=20).fit(df)
    p = tmp_path / "tpm_hgb.joblib"
    save(m, p, meta={"split_hash": "abc"})
    assert p.with_suffix(".json").exists()
    m2 = load(p)
    pd.testing.assert_frame_equal(m.predict(df), m2.predict(df))


def test_mlp_runs_and_evaluate_keys(synthetic_measures):
    df = synthetic_measures(n_profiles=2, n_rows=300)
    m = TrajectoryModel("mlp", targets=("pm",), max_iter=5, hidden_layer_sizes=(4,)).fit(df)
    res = evaluate(m, df, 100)
    assert set(res["pm"]) == {"mse", "max_abs_error", "peak_mae", "n_peaks"}


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        TrajectoryModel("svm")  # type: ignore[arg-type]


@pytest.mark.data
def test_ridge_test_mse_finite_on_real_data():
    if not DATA.exists():
        pytest.skip("no processed data")
    df = pd.read_parquet(DATA)
    s = load_splits(SPLITS)
    train = split_frame(df, s, "train")
    # Few profiles keep the test fast; the fit never sees calib or test.
    train = train[train["profile_id"].isin(s.train[:6])]
    m = TrajectoryModel("ridge", targets=("pm",)).fit(train)
    res = evaluate(m, split_frame(df, s, "test"), 3600)
    assert np.isfinite(res["pm"]["mse"])
