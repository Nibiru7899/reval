"""Calibrate the world on ``train`` + ``reserve`` profiles only (decision R7; AGENTS rule 6).

Mirrors the identification recipe of ``motor.lptn.identify``: 10 s block means of the inputs, zero-order
hold, log-parameters, ``scipy.optimize.least_squares``, and a deterministic profile subsample. ``calib``
and ``test`` profiles are never used for fitting; ``evaluate_world_mse`` reads test profiles for reporting
the model-form discrepancy only.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from motor.splits import Splits, split_frame
from scipy.optimize import least_squares

from bench.world.model import (
    DEFAULT_BOUNDS,
    FIT_NAMES,
    NODES,
    OBSERVED,
    Drive,
    PhysicalParams,
    World,
    WorldParams,
    default_world_params,
    integrate,
    stability_substeps,
)

_STEP_S = 10.0
_STRIDE = 20  # rows per 10 s block at 2 Hz
_OBS_IDX = [NODES.index(n) for n in OBSERVED]


def _pack(frame: pd.DataFrame, ids: list[int], max_blocks: int | None) -> dict[str, np.ndarray]:
    """Block-mean inputs, measured observed temperatures at block boundaries, padded to equal length."""
    parts = []
    for pid in ids:
        g = frame[frame["profile_id"] == pid]
        n_blocks = (len(g) - 1) // _STRIDE
        if max_blocks is not None:
            n_blocks = min(n_blocks, max_blocks)
        if n_blocks < 2:
            continue
        n = n_blocks * _STRIDE
        i_s = np.hypot(g["i_d"].to_numpy(float), g["i_q"].to_numpy(float))[:n]
        u_s = np.hypot(g["u_d"].to_numpy(float), g["u_q"].to_numpy(float))[:n]
        cols = [i_s, u_s] + [g[c].to_numpy(float)[:n] for c in ("motor_speed", "coolant", "ambient")]
        blocks = [c.reshape(n_blocks, _STRIDE).mean(axis=1) for c in cols]
        temps = g[list(OBSERVED)].to_numpy(float)[: n + 1 : _STRIDE]
        parts.append((blocks, temps))
    if not parts:
        raise ValueError("no usable profiles")
    t_max = max(len(b[0]) for b, _ in parts)
    n_b = len(parts)
    drive = [np.zeros((t_max, n_b)) for _ in range(5)]
    temps = np.zeros((t_max + 1, 4, n_b))
    mask = np.zeros((t_max + 1, n_b), dtype=bool)
    for j, (blocks, tp) in enumerate(parts):
        m = len(blocks[0])
        for q in range(5):
            drive[q][:m, j] = blocks[q]
            drive[q][m:, j] = blocks[q][-1]
        temps[: m + 1, :, j] = tp
        temps[m + 1 :, :, j] = tp[-1]
        mask[: m + 1, j] = True
    return {"drive": drive, "temps": temps, "mask": mask}  # type: ignore[dict-item]


def _simulate_packed(
    v: Mapping[str, float], err_w: float, data: dict[str, Any], phys: PhysicalParams
) -> np.ndarray:
    t0 = data["temps"][0]  # (4, B): pm, yoke, tooth, winding
    theta0 = np.stack([t0[0], t0[0], t0[2], t0[1], t0[3], t0[3], t0[1]])
    n_sub = stability_substeps(v, phys, _STEP_S)
    sim = integrate(Drive(*data["drive"]), theta0, _STEP_S, v, phys, err_w, n_sub)
    return sim[:, _OBS_IDX, :]


def _per_node_mse(sim: np.ndarray, data: dict[str, Any]) -> dict[str, float]:
    err = sim - data["temps"]
    return {n: float(np.mean(err[:, i, :][data["mask"]] ** 2)) for i, n in enumerate(OBSERVED)}


def calibrate_world(
    df: pd.DataFrame,
    splits: Splits,
    *,
    base: WorldParams | None = None,
    max_profiles: int = 14,
    max_blocks: int | None = 1500,
    seed: int = 0,
    max_nfev: int = 40,
) -> tuple[World, dict[str, Any]]:
    """Fit the world to ``train`` + ``reserve`` profiles of ``df`` (nothing else is read).

    ``max_blocks`` truncates every profile to its first blocks (1500 blocks = 4.2 h at 10 s) to bound the
    runtime. Returns the calibrated ``World`` and an info dict (train MSE per node, nfev, runtime, ...).
    """
    started = time.perf_counter()
    allowed = sorted({*splits.train, *splits.reserve})
    fit_df = pd.concat([split_frame(df, splits, "train"), split_frame(df, splits, "reserve")])
    assert set(fit_df["profile_id"].unique()) <= set(allowed)  # R7 guard: no calib/test rows
    ids_all = sorted(int(i) for i in fit_df["profile_id"].unique())
    rng = np.random.default_rng(seed)
    ids = sorted(int(i) for i in rng.choice(ids_all, size=min(max_profiles, len(ids_all)), replace=False))
    data = _pack(fit_df, ids, max_blocks)

    base = base or default_world_params()
    lo = np.array([math.log(DEFAULT_BOUNDS[k][0]) for k in FIT_NAMES])
    hi = np.array([math.log(DEFAULT_BOUNDS[k][1]) for k in FIT_NAMES])
    x0 = np.clip(np.log([base.values[k] for k in FIT_NAMES]), lo + 1e-9, hi - 1e-9)
    phys = PhysicalParams()
    mask = data["mask"]

    def to_values(x: np.ndarray) -> dict[str, float]:
        return {k: float(math.exp(c)) for k, c in zip(FIT_NAMES, x, strict=True)}

    def residuals(x: np.ndarray) -> np.ndarray:
        sim = _simulate_packed(to_values(x), base.model_form_error_w, data, phys)
        res = (sim - data["temps"]).transpose(0, 2, 1)[mask]
        return np.nan_to_num(res.ravel(), nan=1.0e3, posinf=1.0e3, neginf=-1.0e3)

    sol = least_squares(
        residuals, x0, bounds=(lo, hi), method="trf", x_scale="jac", diff_step=1e-3, max_nfev=max_nfev
    )
    fitted = WorldParams(to_values(sol.x), base.model_form_error_w, base.sigma_sensor_k)
    mse = _per_node_mse(_simulate_packed(fitted.values, fitted.model_form_error_w, data, phys), data)
    info: dict[str, Any] = {
        "mse_train": mse,
        "nfev": int(sol.nfev),
        "success": bool(sol.success),
        "profiles": ids,
        "fit_splits": ["train", "reserve"],
        "max_blocks": max_blocks,
        "params_at_bound": [
            k for k, v, a, b in zip(FIT_NAMES, sol.x, lo, hi, strict=True) if v - a < 1e-3 or b - v < 1e-3
        ],
        "runtime_s": time.perf_counter() - started,
    }
    return World(fitted), info


def evaluate_world_mse(world: World, df: pd.DataFrame) -> dict[str, float]:
    """Per-node MSE (K^2) of the 10 s resimulation vs measured temperatures on every profile of ``df``.

    Reported as model-form discrepancy (docs/05 section 8); use it on test profiles only for reporting.
    """
    ids = sorted(int(i) for i in df["profile_id"].unique())
    data = _pack(df, ids, None)
    p = world.params
    return _per_node_mse(_simulate_packed(p.values, p.model_form_error_w, data, PhysicalParams()), data)


def dump_world(world: World, path: Path, info: dict[str, Any] | None = None) -> None:
    """Write the world parameters (and optional calibration info) as JSON."""
    doc = {
        "values": dict(world.params.values),
        "model_form_error_w": world.params.model_form_error_w,
        "sigma_sensor_k": world.params.sigma_sensor_k,
        "info": info or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")


def load_world(path: Path) -> World:
    """Inverse of ``dump_world``."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    return World(WorldParams(doc["values"], doc["model_form_error_w"], doc["sigma_sensor_k"]))


def get_world(cache_dir: Path, df: pd.DataFrame, splits: Splits, **kwargs: Any) -> World:
    """Load the calibrated world from ``cache_dir/world.json`` or calibrate once and store it."""
    path = cache_dir / "world.json"
    if path.exists():
        return load_world(path)
    world, info = calibrate_world(df, splits, **kwargs)
    dump_world(world, path, info)
    return world
