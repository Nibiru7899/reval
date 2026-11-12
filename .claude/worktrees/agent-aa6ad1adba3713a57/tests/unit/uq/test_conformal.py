import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from reval.uq import SplitConformal, conformal_quantile, empirical_coverage


def test_quantile_n9_is_ninth_smallest():
    s = np.array([5, 1, 9, 3, 7, 2, 8, 4, 6], dtype=float)
    assert conformal_quantile(s, 0.1) == 9.0


def test_quantile_n5_is_inf_and_interval_none():
    s = np.arange(5, dtype=float)
    assert math.isinf(conformal_quantile(s, 0.1))
    sc = SplitConformal(0.1).fit_scores(s)
    assert sc.interval(1.0) is None
    assert sc.n == 5


def test_no_interpolation():
    s = np.arange(1.0, 20.0)  # n=19, k=ceil(20*0.9)=18
    assert conformal_quantile(s, 0.1) == 18.0


@pytest.mark.parametrize("alpha", [0.0, 1.0, -0.1, 1.5])
def test_bad_alpha(alpha):
    with pytest.raises(ValueError):
        conformal_quantile(np.ones(5), alpha)


def test_empty_scores():
    with pytest.raises(ValueError):
        conformal_quantile(np.array([]), 0.1)


def test_fit_interval_and_coverage():
    sc = SplitConformal(0.2).fit(np.zeros(9), np.arange(1.0, 10.0))
    assert sc.q == 8.0  # k = ceil(10*0.8) = 8
    assert sc.interval(10.0) == (2.0, 18.0)
    assert empirical_coverage(
        np.array([1, 5, 30]), np.array([0, 0, 0]), np.array([2, 4, 40])
    ) == pytest.approx(2 / 3)


def test_unfitted_raises():
    with pytest.raises(RuntimeError):
        _ = SplitConformal(0.1).q


@pytest.mark.slow
@settings(max_examples=5, deadline=None)
@given(alpha=st.sampled_from([0.1, 0.2]))
def test_coverage_on_exchangeable_data(alpha):
    covs = []
    for seed in range(200):
        rng = np.random.default_rng(seed)
        cal = rng.normal(size=100)
        test = rng.normal(size=200)
        sc = SplitConformal(alpha).fit(cal, np.zeros(100))
        lo_hi = sc.interval(0.0)
        assert lo_hi is not None
        covs.append(empirical_coverage(test, np.full(200, lo_hi[0]), np.full(200, lo_hi[1])))
    assert np.mean(covs) >= 1 - alpha - 0.05
