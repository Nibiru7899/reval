"""CQR (Romano et al. 2019) and normalized-score conformal intervals (docs/10 section 5)."""

import math

import numpy as np
import pytest

from reval.uq.conformal import empirical_coverage
from reval.uq.cqr import CQR, NormalizedConformal


def _hetero(n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = rng.uniform(0.0, 1.0, n)
    sigma = 0.2 + 2.0 * x  # noise grows with x
    y = 10 * x + rng.normal(0.0, 1.0, n) * sigma
    return x, y, sigma


def test_cqr_coverage_on_heteroscedastic_data() -> None:
    rng = np.random.default_rng(0)
    alpha = 0.1
    xc, yc, sc = _hetero(2000, rng)
    xt, yt, st = _hetero(4000, rng)
    z = 1.0  # deliberately too narrow a quantile band: CQR must widen it
    cqr = CQR(alpha).fit(yc, 10 * xc - z * sc, 10 * xc + z * sc)
    ivs = [cqr.interval(10 * x - z * s, 10 * x + z * s) for x, s in zip(xt, st, strict=True)]
    assert all(iv is not None for iv in ivs)
    lo = np.array([iv[0] for iv in ivs])  # type: ignore[index]
    hi = np.array([iv[1] for iv in ivs])  # type: ignore[index]
    assert empirical_coverage(yt, lo, hi) >= 1 - alpha - 0.05


def test_cqr_interval_is_none_when_q_infinite() -> None:
    cqr = CQR(0.1).fit(np.array([1.0, 2.0]), np.array([0.0, 1.0]), np.array([2.0, 3.0]))
    assert math.isinf(cqr.q)
    assert cqr.interval(0.0, 1.0) is None


def test_cqr_requires_fit_and_valid_inputs() -> None:
    with pytest.raises(ValueError):
        CQR(1.5)
    with pytest.raises(RuntimeError):
        _ = CQR(0.1).q
    with pytest.raises(ValueError):
        CQR(0.1).fit(np.zeros(3), np.zeros(2), np.zeros(3))
    with pytest.raises(ValueError):
        CQR(0.1).fit(np.zeros(3), np.ones(3), np.zeros(3))  # lo > hi


def test_cqr_can_shrink_a_too_wide_band() -> None:
    rng = np.random.default_rng(1)
    y = rng.normal(0, 1, 500)
    cqr = CQR(0.1).fit(y, np.full(500, -10.0), np.full(500, 10.0))
    assert cqr.q < 0
    iv = cqr.interval(-10.0, 10.0)
    assert iv is not None
    assert iv[1] - iv[0] < 20.0


def test_normalized_conformal_coverage_and_adaptivity() -> None:
    rng = np.random.default_rng(2)
    alpha = 0.1
    xc, yc, sc = _hetero(2000, rng)
    xt, yt, st = _hetero(4000, rng)
    nc = NormalizedConformal(alpha).fit(yc, 10 * xc, sc)
    ivs = [nc.interval(10 * x, s) for x, s in zip(xt, st, strict=True)]
    assert all(iv is not None for iv in ivs)
    lo = np.array([iv[0] for iv in ivs])  # type: ignore[index]
    hi = np.array([iv[1] for iv in ivs])  # type: ignore[index]
    assert empirical_coverage(yt, lo, hi) >= 1 - alpha - 0.05
    assert (hi - lo)[st > 1.5].mean() > (hi - lo)[st < 0.8].mean()


def test_normalized_conformal_rejects_nonpositive_scale() -> None:
    with pytest.raises(ValueError):
        NormalizedConformal(0.1).fit(np.zeros(3), np.zeros(3), np.array([1.0, 0.0, 1.0]))
