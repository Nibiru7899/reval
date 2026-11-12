"""Exploratory-analysis helpers for the motor dataset (docs/05 sections 1-2 and 6).

Sampling is 2 Hz. ``torque`` and ``motor_speed`` are estimates derived from currents and
voltages, not sensor readings.
"""

from __future__ import annotations

import pandas as pd

SAMPLE_HZ = 2.0


def profile_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per profile: size, duration (h), operating ranges and thermal maxima."""
    g = df.groupby("profile_id")
    out = pd.DataFrame({"n_rows": g.size()})
    out["duration_h"] = out["n_rows"] / SAMPLE_HZ / 3600.0
    for col in ("coolant", "ambient", "motor_speed", "torque"):
        out[f"{col}_min"] = g[col].min()
        out[f"{col}_max"] = g[col].max()
    out["pm_max"] = g["pm"].max()
    out["stator_winding_max"] = g["stator_winding"].max()
    return out.reset_index()


def peak_distribution(df: pd.DataFrame, target: str, window_s: float) -> pd.Series:
    """Peaks of ``target`` over non-overlapping windows, never spanning profiles.

    The trailing partial window of each profile is dropped.
    """
    win = round(window_s * SAMPLE_HZ)
    if win < 1:
        raise ValueError("window_s must cover at least one sample")
    peaks: list[float] = []
    for _, g in df.groupby("profile_id", sort=True):
        vals = g[target].to_numpy()
        for k in range(len(vals) // win):
            peaks.append(float(vals[k * win : (k + 1) * win].max()))
    return pd.Series(peaks, name=f"{target}_peak_{int(window_s)}s", dtype=float)
