"""Peak-level split conformal for the trajectory models (docs/04 A5, docs/10 section 12).

One ``SplitConformal`` per (target, length class). Scores are |true peak - predicted peak| over
non-overlapping windows of ``calib`` profiles only. Intervals are in K around the predicted peak.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from motor.models import TrajectoryModel, peaks
from reval.uq.conformal import SplitConformal, empirical_coverage

LENGTH_CLASSES = {"short": 1200, "medium": 3600, "long": 7200}  # window rows at 2 Hz (10 / 30 / 60 min)


class PeakConformal:
    """Per (target, length class) conformal intervals on window peaks."""

    def __init__(self) -> None:
        self.alpha: float | None = None
        self.conformal: dict[tuple[str, str], SplitConformal] = {}

    def _peak_pairs(
        self, model: TrajectoryModel, df: pd.DataFrame, target: str, rows: int
    ) -> tuple[np.ndarray, np.ndarray]:
        pred = model.predict(df)
        pid = df["profile_id"]
        return peaks(df[target], pid, rows), peaks(pred[target], pid, rows)

    def fit(self, model: TrajectoryModel, df_calib: pd.DataFrame, alpha: float) -> PeakConformal:
        """Calibrate on ``calib`` profiles; the caller passes only those rows."""
        self.alpha = alpha
        self.conformal = {}
        for target in model.targets:
            for cls, rows in LENGTH_CLASSES.items():
                true_pk, pred_pk = self._peak_pairs(model, df_calib, target, rows)
                # Zero windows (profile shorter than the class) gives q = inf via the empty-safe path below.
                sc = SplitConformal(alpha)
                if len(true_pk) == 0:
                    sc._q, sc._n = float("inf"), 0
                else:
                    sc.fit(true_pk, pred_pk)
                self.conformal[(target, cls)] = sc
        return self

    def interval(self, target: str, pred_peak: float, length_class: str) -> tuple[float, float] | None:
        """Interval around ``pred_peak`` or None when q is infinite (too few calibration windows)."""
        return self.conformal[(target, length_class)].interval(pred_peak)

    def coverage(self, model: TrajectoryModel, df_test: pd.DataFrame) -> dict[str, dict[str, float]]:
        """Empirical peak coverage per target and length class; NaN when the interval is unbounded."""
        out: dict[str, dict[str, float]] = {}
        for target in model.targets:
            out[target] = {}
            for cls, rows in LENGTH_CLASSES.items():
                sc = self.conformal[(target, cls)]
                true_pk, pred_pk = self._peak_pairs(model, df_test, target, rows)
                if len(true_pk) == 0 or sc.interval(0.0) is None:
                    out[target][cls] = float("nan")
                    continue
                out[target][cls] = empirical_coverage(true_pk, pred_pk - sc.q, pred_pk + sc.q)
        return out
