import math

import numpy as np
from motor.conformal import LENGTH_CLASSES, PeakConformal
from motor.models import TrajectoryModel


def test_peak_conformal_fit_interval_coverage(synthetic_measures):
    df = synthetic_measures(n_profiles=6, n_rows=1500, seed=1)
    train, calib, test = df[df.profile_id < 13], df[df.profile_id.isin([13, 14])], df[df.profile_id == 15]
    m = TrajectoryModel("ridge", targets=("pm",)).fit(train)
    pc = PeakConformal().fit(m, calib, alpha=0.1)
    assert set(pc.conformal) == {("pm", c) for c in LENGTH_CLASSES}
    # 2 profiles x 1 window of 1200 rows => n=2 < 9 => unbounded
    assert pc.conformal[("pm", "short")].n == 2
    assert pc.interval("pm", 50.0, "short") is None
    cov = pc.coverage(m, test)
    assert set(cov["pm"]) == set(LENGTH_CLASSES)
    assert all(math.isnan(v) for v in cov["pm"].values())


def test_peak_conformal_finite_with_enough_windows(synthetic_measures):
    df = synthetic_measures(n_profiles=8, n_rows=1500, seed=2)
    m = TrajectoryModel("ridge", targets=("pm",)).fit(df[df.profile_id < 12])
    calib = df[df.profile_id >= 12]
    pc = PeakConformal().fit(m, calib, alpha=0.3)  # 6 windows of 1200 rows, k=ceil(7*0.7)=5 <= 6
    iv = pc.interval("pm", 50.0, "short")
    assert iv is not None and iv[0] < 50.0 < iv[1]
    cov = pc.coverage(m, calib)
    assert 0.0 <= cov["pm"]["short"] <= 1.0
    assert not np.isnan(cov["pm"]["short"])
