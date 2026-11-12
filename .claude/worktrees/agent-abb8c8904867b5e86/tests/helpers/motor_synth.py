"""Tiny synthetic motor frames with the real column names, for fast unit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

COLUMNS = (
    "u_q",
    "coolant",
    "stator_winding",
    "u_d",
    "stator_tooth",
    "motor_speed",
    "i_d",
    "i_q",
    "pm",
    "stator_yoke",
    "ambient",
    "torque",
    "profile_id",
)

# (time constant in samples, gain in K per A^2, offset above coolant in K) per temperature.
_THERMAL = {
    "stator_winding": (300.0, 8.0e-4, 5.0),
    "stator_tooth": (450.0, 6.0e-4, 3.0),
    "stator_yoke": (600.0, 4.0e-4, 2.0),
    "pm": (900.0, 3.0e-4, 4.0),
}


def _first_order(drive: np.ndarray, tau: float, start: float) -> np.ndarray:
    alpha = 1.0 / tau
    out = np.empty_like(drive)
    x = start
    for k, d in enumerate(drive):
        x += alpha * (d - x)
        out[k] = x
    return out


def _piecewise(rng: np.random.Generator, n: int, lo: float, hi: float, hold: int) -> np.ndarray:
    n_seg = n // hold + 1
    return np.repeat(rng.uniform(lo, hi, n_seg), hold)[:n]


def synthetic_measures(n_profiles: int = 3, n_rows: int = 600, seed: int = 0) -> pd.DataFrame:
    """Deterministic frame with exactly the raw dataset columns.

    Physical scale (not the standardized scale of the real CSV): currents 0-250 A, speed 0-6000 rpm,
    coolant 18-70 C. Temperatures are first-order responses (tau of hundreds of samples) to i_s^2.
    """
    rng = np.random.default_rng(seed)
    frames = []
    for p in range(n_profiles):
        i_s = _piecewise(rng, n_rows, 0.0, 250.0, 60)
        angle = rng.uniform(0.3, 1.2)
        i_q = i_s * np.cos(angle)
        i_d = -i_s * np.sin(angle)
        speed = _piecewise(rng, n_rows, 0.0, 6000.0, 90)
        coolant = 18.0 + (70.0 - 18.0) * np.clip(
            _first_order(_piecewise(rng, n_rows, 0.0, 1.0, 200), 150.0, 0.2), 0.0, 1.0
        )
        ambient = np.full(n_rows, rng.uniform(18.0, 30.0))
        u_q = 0.001 * speed + 0.1 * i_q
        u_d = -0.0005 * speed + 0.1 * i_d
        torque = 0.4 * i_q
        cols: dict[str, np.ndarray] = {}
        for name, (tau, gain, offset) in _THERMAL.items():
            target = coolant + offset + gain * i_s**2
            series = _first_order(target, tau, float(target[0]))
            cols[name] = series + rng.normal(0.0, 0.05, n_rows)
        frame = pd.DataFrame(
            {
                "u_q": u_q,
                "coolant": coolant,
                "stator_winding": cols["stator_winding"],
                "u_d": u_d,
                "stator_tooth": cols["stator_tooth"],
                "motor_speed": speed,
                "i_d": i_d,
                "i_q": i_q,
                "pm": cols["pm"],
                "stator_yoke": cols["stator_yoke"],
                "ambient": ambient,
                "torque": torque,
                "profile_id": np.full(n_rows, 10 + p, dtype=np.int64),
            }
        )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)[list(COLUMNS)]
