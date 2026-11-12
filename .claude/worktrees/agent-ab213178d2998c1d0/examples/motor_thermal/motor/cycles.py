"""Duty-cycle generator and subject library (docs/05 section 6).

Units: torque N*m, motor_speed rpm, coolant and ambient deg C (absolute), t in s, 2 Hz sampling.

Library design choices (recorded, see also docs/log):
* Parametric cycles draw each block's (torque, speed) from a random *steady real train* row (central
  98 percent), so the operating points are jointly plausible and inside the drive-map domain;
  coolant and ambient also come from a real train row.
* Every 5th parametric cycle (8 of 40) is deliberately pushed *outside* the train envelope (one of
  speed, torque, coolant above the train 99.5 percent quantile) so applicability gating
  has something to catch. The other 80 percent are inside.
* Recorded cycles come from ``splits.test`` only, never ``reserve`` (AGENTS rule 6, R5).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd

from motor.drive_map import steady_mask

if TYPE_CHECKING:
    from motor.splits import Splits

HZ = 2
DT_S = 1.0 / HZ
# Cycle durations (s) cycled through the three conformal length classes (10 / 30 / 60 min).
CLASS_DURATIONS_S = {"short": 600, "medium": 1800, "long": 3600}
N_PARAMETRIC = 40
N_RECORDED = 40
_OUTSIDE_EVERY = 5
_MIN_BLOCK_S = 60
DEFAULT_PARQUET = Path(__file__).resolve().parents[1] / "data" / "processed" / "measures.parquet"
_COLUMNS = ("torque", "motor_speed", "coolant", "ambient")


def blocks(params: Mapping[str, Any]) -> pd.DataFrame:
    """Piecewise-constant duty cycle at 2 Hz.

    ``params = {"blocks": [[torque_Nm, speed_rpm, duration_s], ...], "coolant": degC, "ambient": degC}``.
    Returns torque, motor_speed, coolant, ambient and t (s, starting at 0).
    """
    spec = params["blocks"]
    if not spec:
        raise ValueError("blocks must be non-empty")
    torque: list[np.ndarray] = []
    speed: list[np.ndarray] = []
    for torque_nm, speed_rpm, duration_s in spec:
        n = round(float(duration_s) * HZ)
        if n <= 0:
            raise ValueError(f"block duration must be positive, got {duration_s}")
        torque.append(np.full(n, float(torque_nm)))
        speed.append(np.full(n, float(speed_rpm)))
    tq = np.concatenate(torque)
    return pd.DataFrame(
        {
            "torque": tq,
            "motor_speed": np.concatenate(speed),
            "coolant": np.full(len(tq), float(params["coolant"])),
            "ambient": np.full(len(tq), float(params["ambient"])),
            "t": np.arange(len(tq)) * DT_S,
        }
    )


def recorded(
    profile_id: int,
    start_s: float,
    duration_s: float,
    df: pd.DataFrame,
    *,
    splits: Splits | None = None,
) -> pd.DataFrame:
    """A real segment of one profile (t restarted at 0). Test profiles only when ``splits`` is given."""
    if splits is not None and splits.of(int(profile_id)) != "test":
        raise ValueError(f"profile {profile_id} is not a test profile; recorded cycles use test only")
    seg = _segment(profile_id, start_s, duration_s, df)
    out = seg[list(_COLUMNS)].reset_index(drop=True)
    out["t"] = np.arange(len(out)) * DT_S
    return out


def recorded_temperatures(
    profile_id: int, start_s: float, duration_s: float, df: pd.DataFrame
) -> pd.DataFrame:
    """Measured pm and stator_winding (deg C) over the same segment, for Tier A ground truth."""
    seg = _segment(profile_id, start_s, duration_s, df)
    return seg[["pm", "stator_winding"]].reset_index(drop=True)


def _segment(profile_id: int, start_s: float, duration_s: float, df: pd.DataFrame) -> pd.DataFrame:
    prof = df[df["profile_id"] == profile_id]
    if prof.empty:
        raise ValueError(f"profile {profile_id} not in the data")
    i0 = round(float(start_s) * HZ)
    n = round(float(duration_s) * HZ)
    if i0 < 0 or n <= 0 or i0 + n > len(prof):
        raise ValueError(
            f"segment at {start_s} s for {duration_s} s outside profile {profile_id} ({len(prof) * DT_S} s)"
        )
    return prof.sort_values("t").iloc[i0 : i0 + n]


def length_class(duration_s: float) -> Literal["short", "medium", "long"]:
    """Conformal length class, rounded *up* (conservative): <=10 min short, <=30 min medium, else long."""
    if duration_s <= CLASS_DURATIONS_S["short"]:
        return "short"
    if duration_s <= CLASS_DURATIONS_S["medium"]:
        return "medium"
    return "long"


def _partition(rng: np.random.Generator, total_s: int, n_blocks: int) -> list[int]:
    """Split ``total_s`` into ``n_blocks`` integer durations of at least _MIN_BLOCK_S each."""
    spare = total_s - n_blocks * _MIN_BLOCK_S
    cuts = np.sort(rng.integers(0, spare + 1, n_blocks - 1)) if n_blocks > 1 else np.array([], dtype=int)
    edges = np.concatenate([[0], cuts, [spare]])
    return [int(d) + _MIN_BLOCK_S for d in np.diff(edges)]


def _parametric(
    rng: np.random.Generator, idx: int, ops: pd.DataFrame, env: Mapping[str, tuple[float, float]]
) -> dict[str, Any]:
    cls = ("short", "medium", "long")[idx % 3]
    total = CLASS_DURATIONS_S[cls]
    n_blocks = int(rng.integers(2, 7))
    durations = _partition(rng, total, n_blocks)
    picks = ops.iloc[rng.integers(0, len(ops), n_blocks)]
    spec = [
        [round(float(t), 1), round(float(w), 0), d]
        for t, w, d in zip(picks["torque"], picks["motor_speed"], durations, strict=True)
    ]
    env_row = ops.iloc[int(rng.integers(0, len(ops)))]
    coolant = round(float(env_row["coolant"]), 1)
    ambient = round(float(env_row["ambient"]), 1)
    if idx % _OUTSIDE_EVERY == _OUTSIDE_EVERY - 1:
        kind = (idx // _OUTSIDE_EVERY) % 3
        j = int(rng.integers(0, n_blocks))
        if kind == 0:  # speed beyond the train maximum
            spec[j][1] = round(env["motor_speed"][1] * float(rng.uniform(1.1, 1.4)), 0)
        elif kind == 1:  # torque beyond the train maximum
            spec[j][0] = round(env["torque"][1] * float(rng.uniform(1.1, 1.4)), 1)
        else:  # coolant hotter than anything in train
            coolant = round(env["coolant"][1] + float(rng.uniform(5.0, 20.0)), 1)
    return {
        "id": f"DC-P{idx + 1:02d}",
        "kind": "duty_cycle",
        "generator": "motor.cycles:blocks",
        "params": {"blocks": spec, "coolant": coolant, "ambient": ambient},
    }


def make_library(
    seed: int, splits: Splits, *, data: pd.DataFrame | None = None, parquet: Path = DEFAULT_PARQUET
) -> list[dict[str, Any]]:
    """40 parametric + 40 recorded subjects, deterministic in (seed, data, splits).

    ``data`` is the prepared measures frame (loaded from ``parquet`` when omitted); it supplies the
    train operating points/envelope and the length of each test profile. Each entry has ``id``,
    ``kind``, ``generator`` and ``params`` (the manifest ``subjects:`` format).
    """
    df = data if data is not None else pd.read_parquet(parquet)
    rng = np.random.default_rng(seed)
    train = df[df["profile_id"].isin(splits.train)]
    # Operating points: steady train rows inside the central 98 percent of torque and speed, so the
    # "inside" cycles are inside the drive map's own domain (rare tails would trip its range box).
    steady = train.loc[steady_mask(train)]
    central = np.ones(len(steady), dtype=bool)
    for c in ("torque", "motor_speed"):
        lo, hi = steady[c].quantile(0.01), steady[c].quantile(0.99)
        central &= ((steady[c] >= lo) & (steady[c] <= hi)).to_numpy()
    pool = steady.loc[central]
    if pool.empty:
        raise ValueError("no steady train rows to draw operating points from")
    ops = pool.iloc[:: max(1, len(pool) // 20_000)][list(_COLUMNS)].reset_index(drop=True)
    env = {c: (float(train[c].quantile(0.005)), float(train[c].quantile(0.995))) for c in _COLUMNS}
    out = [_parametric(rng, i, ops, env) for i in range(N_PARAMETRIC)]

    lengths = df[df["profile_id"].isin(splits.test)].groupby("profile_id").size() * DT_S
    pids = sorted(int(p) for p in splits.test)
    classes = ("short", "medium", "long")
    for i in range(N_RECORDED):
        dur = CLASS_DURATIONS_S[classes[i % 3]]
        eligible = [p for p in pids if lengths[p] >= dur]
        if not eligible:
            raise ValueError(f"no test profile is at least {dur} s long")
        pid = eligible[(i // 3) % len(eligible)]
        start = round(float(rng.uniform(0.0, lengths[pid] - dur)) * HZ) / HZ
        out.append(
            {
                "id": f"DC-R{i + 1:02d}",
                "kind": "duty_cycle",
                "generator": "motor.cycles:recorded",
                "params": {"profile_id": pid, "start_s": start, "duration_s": float(dur)},
            }
        )
    return out
