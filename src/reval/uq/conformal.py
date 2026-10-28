"""Split-conformal prediction intervals (docs/04 A5). Pure numpy; no I/O."""

from __future__ import annotations

import math

import numpy as np


def conformal_quantile(scores: np.ndarray, alpha: float) -> float:
    """Finite-sample conformal quantile: the ceil((n+1)(1-alpha))-th smallest score, else inf.

    Deliberately not ``np.quantile``: interpolation would break the coverage guarantee.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    s = np.asarray(scores, dtype=float).ravel()
    n = len(s)
    if n == 0:
        raise ValueError("scores must be non-empty")
    k = math.ceil((n + 1) * (1.0 - alpha))
    if k > n:
        return math.inf
    return float(np.sort(s)[k - 1])


class SplitConformal:
    """Symmetric absolute-residual split conformal interval."""

    def __init__(self, alpha: float) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        self.alpha = alpha
        self._q: float | None = None
        self._n = 0

    def fit(self, y_true: np.ndarray, y_pred: np.ndarray) -> SplitConformal:
        """Calibrate on |y_true - y_pred|."""
        return self.fit_scores(np.abs(np.asarray(y_true, float) - np.asarray(y_pred, float)))

    def fit_scores(self, scores: np.ndarray) -> SplitConformal:
        """Calibrate on precomputed nonnegative scores."""
        s = np.asarray(scores, dtype=float).ravel()
        if np.any(s < 0):
            raise ValueError("scores must be nonnegative")
        self._q = conformal_quantile(s, self.alpha)
        self._n = len(s)
        return self

    def interval(self, y_pred: float) -> tuple[float, float] | None:
        """(y_pred - q, y_pred + q), or None when q is infinite (too few calibration scores)."""
        q = self.q
        if math.isinf(q):
            return None
        return (y_pred - q, y_pred + q)

    @property
    def q(self) -> float:
        if self._q is None:
            raise RuntimeError("SplitConformal is not fitted")
        return self._q

    @property
    def n(self) -> int:
        return self._n


def empirical_coverage(y_true: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    """Fraction of y_true inside [lo, hi]."""
    y = np.asarray(y_true, dtype=float)
    if y.size == 0:
        raise ValueError("empty input")
    return float(np.mean((y >= np.asarray(lo, float)) & (y <= np.asarray(hi, float))))
