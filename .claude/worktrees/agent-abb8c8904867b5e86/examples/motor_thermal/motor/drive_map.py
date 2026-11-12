"""Drive map: (torque, motor_speed) -> (i_d, i_q, u_d, u_q) (docs/05 section 5).

Duty cycles are written in engineer terms; the trajectory models need currents and voltages.
The map is fitted on *steady* train rows only, and it carries its own applicability domain over
(torque N*m, motor_speed rpm). Coolant and ambient (deg C) pass through unchanged.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from motor.features import INPUT_COLUMNS
from reval.uq.domain import ApplicabilityDomain, DomainReport

OUTPUTS = ("i_d", "i_q", "u_d", "u_q")
DOMAIN_FEATURES = ("torque", "motor_speed")
STEADY_WINDOW_ROWS = 20  # 10 s at 2 Hz
SPEED_TOL_RPM = 50.0
TORQUE_TOL_NM = 5.0
MAX_FIT_ROWS = 150_000
_AD_HOLDOUT_EVERY = 5  # every 5th train profile calibrates the domain threshold tau


def steady_mask(
    df: pd.DataFrame,
    window: int = STEADY_WINDOW_ROWS,
    speed_tol: float = SPEED_TOL_RPM,
    torque_tol: float = TORQUE_TOL_NM,
) -> pd.Series:
    """Rows where speed and torque each vary less than their tolerance over ``window`` rows (per profile)."""
    g = df.groupby("profile_id", sort=False)
    ok = pd.Series(True, index=df.index)
    for col, tol in (("motor_speed", speed_tol), ("torque", torque_tol)):
        span = g[col].transform(lambda s: s.rolling(window, center=True, min_periods=window).max()) - g[
            col
        ].transform(lambda s: s.rolling(window, center=True, min_periods=window).min())
        ok &= (span < tol).fillna(False)
    return ok


class DriveMap:
    """Regression from the torque-speed plane to dq currents and voltages, with its own domain."""

    def __init__(self) -> None:
        self.models: dict[str, HistGradientBoostingRegressor] = {}
        self.ad: ApplicabilityDomain | None = None

    def fit(self, df_train: pd.DataFrame) -> DriveMap:
        """Fit one HGB per output on steady rows and the (torque, speed) applicability domain."""
        steady = df_train.loc[steady_mask(df_train)]
        if len(steady) < 50:
            raise ValueError(f"only {len(steady)} steady rows; cannot fit the drive map")
        if len(steady) > MAX_FIT_ROWS:
            steady = steady.sample(MAX_FIT_ROWS, random_state=0).sort_index()
        x = steady[list(DOMAIN_FEATURES)].to_numpy(dtype=float)
        self.models = {
            out: HistGradientBoostingRegressor(random_state=0).fit(x, steady[out].to_numpy(dtype=float))
            for out in OUTPUTS
        }
        # Profile-level hold-out for tau (never row-level; AGENTS rule 6). With <5 profiles, reuse the rows.
        pids = sorted(steady["profile_id"].unique())
        held = {p for i, p in enumerate(pids) if i % _AD_HOLDOUT_EVERY == _AD_HOLDOUT_EVERY - 1}
        is_held = steady["profile_id"].isin(held).to_numpy()
        if is_held.sum() == 0 or (~is_held).sum() == 0:
            x_fit, x_cal = x, x
        else:
            x_fit, x_cal = x[~is_held], x[is_held]
        self.ad = ApplicabilityDomain(DOMAIN_FEATURES).fit(x_fit, x_cal)
        return self

    def _require_fit(self) -> ApplicabilityDomain:
        if self.ad is None or not self.models:
            raise RuntimeError("DriveMap is not fitted")
        return self.ad

    def predict(self, torque: np.ndarray, speed: np.ndarray) -> pd.DataFrame:
        """Predicted i_d, i_q, u_d, u_q for the given torque-speed points."""
        self._require_fit()
        x = np.column_stack([np.asarray(torque, dtype=float), np.asarray(speed, dtype=float)])
        return pd.DataFrame({o: m.predict(x) for o, m in self.models.items()})

    def to_inputs(
        self,
        torque: np.ndarray,
        speed: np.ndarray,
        coolant: float | np.ndarray,
        ambient: float | np.ndarray,
    ) -> pd.DataFrame:
        """INPUT_COLUMNS for a 2 Hz duty cycle (one row per torque sample; no profile_id or t)."""
        torque = np.asarray(torque, dtype=float)
        speed = np.asarray(speed, dtype=float)
        if torque.shape != speed.shape or torque.ndim != 1:
            raise ValueError("torque and speed must be 1-D arrays of equal length")
        out = self.predict(torque, speed)
        out["motor_speed"] = speed
        out["coolant"] = np.broadcast_to(np.asarray(coolant, dtype=float), speed.shape).copy()
        out["ambient"] = np.broadcast_to(np.asarray(ambient, dtype=float), speed.shape).copy()
        return out[list(INPUT_COLUMNS)]

    def domain_report(self, torque: np.ndarray, speed: np.ndarray) -> DomainReport:
        """Applicability of the drive map itself at these operating points (strict)."""
        ad = self._require_fit()
        x = np.column_stack([np.asarray(torque, dtype=float), np.asarray(speed, dtype=float)])
        return ad.check(x)

    def r2(self, df: pd.DataFrame, *, steady_only: bool = True) -> dict[str, Any]:
        """Held-out R^2 per output (and row count) on ``df``; steady rows only by default."""
        self._require_fit()
        sub = df.loc[steady_mask(df)] if steady_only else df
        pred = self.predict(sub["torque"].to_numpy(), sub["motor_speed"].to_numpy())
        res: dict[str, Any] = {"n_rows": len(sub)}
        for o in OUTPUTS:
            y = sub[o].to_numpy(dtype=float)
            ss_res = float(np.sum((y - pred[o].to_numpy()) ** 2))
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            res[o] = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        return res
