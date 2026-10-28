"""Tier B base snapshots: replace measured temperatures with world trajectories and retrain (R7).

``build_tier_b_base`` edits a workspace (a clone of the motor project with data in place):
1. every profile's four node temperatures become the world's noise-free trajectory (``World.simulate``
   with ``physical_params``), started from the recorded first-row state;
2. ``scripts/train.py``, ``scripts/calibrate.py`` and ``scripts/calibrate_lptn.py`` are rerun there;
3. ``reval snapshot --write`` writes the lock;
4. ``bench_measurements.json`` is written next to the manifest. It is deliberately **not** a declared
   artifact: it is the "physical world", so a T9 drift in it stays invisible to ReVal.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from bench.world.model import (
    NODES,
    OBSERVED,
    Drive,
    PhysicalParams,
    World,
    initial_state,
    integrate,
    stability_substeps,
)

MODELS: tuple[str, ...] = ("ridge", "hgb", "mlp")
TARGETS: tuple[str, ...] = ("pm", "stator_winding")
_PREFIX = {"pm": "tpm", "stator_winding": "tsw"}
_QUANTITY = {"pm": "pm_peak", "stator_winding": "sw_peak"}
MEASUREMENTS_FILE = "bench_measurements.json"
_HZ = 2


def _root(workspace: Any) -> Path:
    """Project root of a workspace: ``.root``/``.path`` attribute, or the path itself."""
    if isinstance(workspace, (str, Path)):
        return Path(workspace)
    for attr in ("root", "path"):
        value = getattr(workspace, attr, None)
        if value is not None:
            return Path(value)
    return Path(workspace)


def world_trajectories(world: World, df: pd.DataFrame, phys: PhysicalParams) -> pd.DataFrame:
    """Copy of ``df`` whose ``OBSERVED`` columns are the world's noise-free trajectory per profile.

    Profiles are integrated as one padded batch (inputs held at their last value past the end). Row t
    keeps the recorded state of row 0 as the initial condition and is the state *before* row t's input
    acts, as in ``World.simulate``.
    """
    df = df.sort_values(["profile_id", "t"]).reset_index(drop=True)
    groups = [(pid, g) for pid, g in df.groupby("profile_id", sort=True)]
    t_max = max(len(g) for _, g in groups)
    n_b = len(groups)
    arrs = [np.zeros((t_max, n_b)) for _ in range(5)]
    theta0 = np.zeros((7, n_b))
    for j, (_, g) in enumerate(groups):
        cols = (
            np.hypot(g["i_d"].to_numpy(float), g["i_q"].to_numpy(float)),
            np.hypot(g["u_d"].to_numpy(float), g["u_q"].to_numpy(float)),
            g["motor_speed"].to_numpy(float),
            g["coolant"].to_numpy(float),
            g["ambient"].to_numpy(float),
        )
        for q, c in enumerate(cols):
            arrs[q][: len(g), j] = c
            arrs[q][len(g) :, j] = c[-1]
        theta0[:, j] = initial_state(g)
    n_sub = stability_substeps(world.params.values, phys, 1.0 / _HZ)
    traj = integrate(
        Drive(*arrs), theta0, 1.0 / _HZ, world.params.values, phys, world.params.model_form_error_w, n_sub
    )
    out = df.copy()
    for j, (_, g) in enumerate(groups):
        for name in OBSERVED:
            out.loc[g.index, name] = traj[: len(g), NODES.index(name), j]
    return out


def crn_rng(seed: int | str, subject_id: str) -> np.random.Generator:
    """Common-random-number generator for a bench measurement (docs/06 section 2).

    ``seed`` plays the role of the scenario id; the producer id is fixed to ``bench_measure``.
    """
    digest = hashlib.sha256(f"{seed}|bench_measure|{subject_id}".encode()).hexdigest()
    return np.random.default_rng(int(digest[:8], 16))


def bench_measurements(
    world: World, df: pd.DataFrame, subjects: dict[str, Any], phys: PhysicalParams, seed: int | str
) -> dict[str, dict[str, float]]:
    """Measured peaks of every recorded-cycle subject: ``{subject_id: {quantity: peak}}``.

    ``df`` must already hold the world trajectories. The pm and winding columns of the recorded segment
    get the sensor offset (pm only) and ``N(0, sigma_sensor)`` noise from the subject's CRN generator.
    """
    sigma = world.params.sigma_sensor_k
    table: dict[str, dict[str, float]] = {}
    for sid in sorted(subjects):
        spec = subjects[sid]
        if spec.get("generator") != "motor.cycles:recorded":
            continue
        p = spec["params"]
        prof = df[df["profile_id"] == int(p["profile_id"])].sort_values("t")
        i0, n = round(float(p["start_s"]) * _HZ), round(float(p["duration_s"]) * _HZ)
        seg = prof.iloc[i0 : i0 + n]
        rng = crn_rng(seed, sid)
        noise = rng.normal(0.0, sigma, size=(len(seg), 4))  # same draw layout as World.measure
        pm = seg["pm"].to_numpy(float) + noise[:, 0] + phys.sensor_offset
        sw = seg["stator_winding"].to_numpy(float) + noise[:, 3]
        table[sid] = {_QUANTITY["pm"]: float(pm.max()), _QUANTITY["stator_winding"]: float(sw.max())}
    return table


def _run(root: Path, args: Sequence[str]) -> None:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed in {root}:\n{proc.stdout[-800:]}\n{proc.stderr[-1500:]}")


def build_tier_b_base(
    workspace: Any,
    world: World,
    physical_params: PhysicalParams,
    seed: int,
    *,
    models: Sequence[str] = MODELS,
    lptn_args: Sequence[str] = ("--max-profiles", "12", "--max-nfev", "60"),
    max_workers: int = 6,
    write_lock: bool = True,
) -> None:
    """Make the workspace's data, models and lock refer to the world plant (see module docstring).

    ``workspace`` is a ``bench.harness`` Workspace (anything with ``.root`` or ``.path``) or a project
    path. ``seed`` seeds the common-random-number measurement table (used as the scenario id).
    """
    root = _root(workspace)
    parquet = root / "data" / "processed" / "measures.parquet"
    df = pd.read_parquet(parquet)
    replaced = world_trajectories(world, df, physical_params)
    # Write-then-replace: the workspace may hardlink data/ from a shared cache; never modify it in place.
    tmp = parquet.with_name(parquet.name + ".tmp")
    replaced.to_parquet(tmp, index=False)
    os.replace(tmp, parquet)

    pairs = [(m, t) for m in models for t in TARGETS]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(
            pool.map(lambda mt: _run(root, ["scripts/train.py", "--model", mt[0], "--target", mt[1]]), pairs)
        )
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(
            pool.map(
                lambda mt: _run(
                    root, ["scripts/calibrate.py", "--model-artifact", f"{_PREFIX[mt[1]]}_{mt[0]}"]
                ),
                pairs,
            )
        )
    _run(root, ["scripts/calibrate_lptn.py", *lptn_args])

    subjects = yaml.safe_load((root / "subjects.yaml").read_text(encoding="utf-8"))
    table = bench_measurements(world, replaced, subjects, physical_params, seed)
    (root / MEASUREMENTS_FILE).write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")
    if not write_lock:
        return
    proc = subprocess.run(
        [sys.executable, "-m", "reval.cli.main", "snapshot", "--write"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"reval snapshot --write failed:\n{proc.stdout[-500:]}\n{proc.stderr[-1000:]}")
