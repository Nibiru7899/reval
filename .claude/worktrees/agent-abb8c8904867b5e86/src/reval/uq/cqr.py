"""Conformalized quantile regression (Romano et al. 2019) and normalized-score conformal. Pure numpy.

CQR: given lower/upper quantile predictions, the score is ``E = max(q_lo - y, y - q_hi)`` and the
interval is ``[q_lo - Q, q_hi + Q]`` with ``Q`` the finite-sample conformal quantile of the calibration
scores. ``Q`` may be negative (a too-wide band is shrunk), unlike the absolute-residual scores of
:class:`reval.uq.conformal.SplitConformal`.
"""

from __future__ import annotations

import math

import numpy as np

from reval.uq.conformal import conformal_quantile


def _check_alpha(alpha: float) -> None:
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")


class CQR:
    """Split-conformal CQR on precomputed lower/upper quantile predictions (docs/10 section 5)."""

    def __init__(self, alpha: float) -> None:
        _check_alpha(alpha)
        self.alpha = alpha
        self._q: float | None = None
        self._n = 0

    def fit(self, y_true: np.ndarray, q_lo: np.ndarray, q_hi: np.ndarray) -> CQR:
        """Calibrate on ``max(q_lo - y, y - q_hi)``."""
        y, lo, hi = (np.asarray(a, dtype=float).ravel() for a in (y_true, q_lo, q_hi))
        if not (len(y) == len(lo) == len(hi)):
            raise ValueError("y_true, q_lo and q_hi must have the same length")
        if np.any(lo > hi):
            raise ValueError("q_lo must not exceed q_hi")
        self._q = conformal_quantile(np.maximum(lo - y, y - hi), self.alpha)
        self._n = len(y)
        return self

    def interval(self, q_lo: float, q_hi: float) -> tuple[float, float] | None:
        """``(q_lo - Q, q_hi + Q)``, or None when Q is infinite (too few calibration scores)."""
        q = self.q
        if math.isinf(q):
            return None
        return (q_lo - q, q_hi + q)

    @property
    def q(self) -> float:
        if self._q is None:
            raise RuntimeError("CQR is not fitted")
        return self._q

    @property
    def n(self) -> int:
        return self._n


class NormalizedConformal:
    """Locally adaptive split conformal with scores ``|y - y_hat| / sigma`` (sigma > 0)."""

    def __init__(self, alpha: float) -> None:
        _check_alpha(alpha)
        self.alpha = alpha
        self._q: float | None = None

    def fit(self, y_true: np.ndarray, y_pred: np.ndarray, sigma: np.ndarray) -> NormalizedConformal:
        """Calibrate on ``|y_true - y_pred| / sigma``."""
        y, p, s = (np.asarray(a, dtype=float).ravel() for a in (y_true, y_pred, sigma))
        if not (len(y) == len(p) == len(s)):
            raise ValueError("y_true, y_pred and sigma must have the same length")
        if np.any(s <= 0):
            raise ValueError("sigma must be positive")
        self._q = conformal_quantile(np.abs(y - p) / s, self.alpha)
        return self

    def interval(self, y_pred: float, sigma: float) -> tuple[float, float] | None:
        """``y_pred +- q * sigma``, or None when q is infinite."""
        if sigma <= 0:
            raise ValueError("sigma must be positive")
        q = self.q
        if math.isinf(q):
            return None
        return (y_pred - q * sigma, y_pred + q * sigma)

    @property
    def q(self) -> float:
        if self._q is None:
            raise RuntimeError("NormalizedConformal is not fitted")
        return self._q
