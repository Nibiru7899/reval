"""Design optimizer O1/O2/O3 (docs/04 A8, docs/10 section 12). Example code, not part of the ReVal core.

Maximize delivered mechanical energy of a 3-block duty cycle subject to the thermal limits:

* O1: point prediction ``peak(y_hat) <= L`` (no uncertainty).
* O2: conformal upper bound ``peak(y_hat) + q <= L`` (fail closed: an unbounded interval is infeasible).
* O3: O2 plus the model's applicability domain (penalty on the kNN distance above tau and on box exits).

Units: torque N*m, speed rpm, durations s, temperatures deg C (limits) and K (intervals).
The solver is seeded ``differential_evolution`` with one worker, so a run is reproducible.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from motor.cycles import HZ, blocks, length_class
from motor.drive_map import DriveMap
from motor.models import TrajectoryModel
from reval.uq.domain import ApplicabilityDomain, DomainReport

DURATIONS_S: tuple[float, float, float] = (600.0, 900.0, 300.0)
COOLANT_C = 27.0  # about the train median (26.7 degC), rounded
AMBIENT_C = 24.0  # about the train median (24.1 degC), rounded
LIMIT_KEYS = {"pm": "pm_peak_limit_degC", "stator_winding": "sw_peak_limit_degC"}
_PENALTY = 1e3  # per unit of normalized violation; dwarfs the (normalized) energy term in [0, 1]
_INFEASIBLE = 1e3  # penalty for an unbounded (q = inf) interval


@dataclass(frozen=True)
class OptResult:
    """Optimum of one variant. ``theta`` = [torque_1, speed_1, torque_2, speed_2, torque_3, speed_3]."""

    theta: np.ndarray
    subject_params: dict[str, Any]
    pred_peak: float
    upper: float | None
    ad_report: DomainReport


def subject_params(theta: Sequence[float], coolant: float, ambient: float) -> dict[str, Any]:
    """The ``cycles.blocks`` parameter dict for ``theta``."""
    th = [float(v) for v in theta]
    return {
        "blocks": [[th[2 * i], th[2 * i + 1], DURATIONS_S[i]] for i in range(3)],
        "coolant": float(coolant),
        "ambient": float(ambient),
    }


def energy_J(theta: Sequence[float]) -> float:
    """Delivered mechanical energy, sum of torque * omega * duration (omega in rad/s)."""
    th = np.asarray(theta, dtype=float)
    return float(sum(th[2 * i] * th[2 * i + 1] * 2.0 * math.pi / 60.0 * DURATIONS_S[i] for i in range(3)))


def _energy_scale(bounds: Sequence[tuple[float, float]]) -> float:
    """Largest attainable |energy| over the bound corners; keeps the energy term in [-1, 1]."""
    best = 0.0
    for i in range(3):
        t = max(abs(bounds[2 * i][0]), abs(bounds[2 * i][1]))
        w = max(abs(bounds[2 * i + 1][0]), abs(bounds[2 * i + 1][1]))
        best += t * w * 2.0 * math.pi / 60.0 * DURATIONS_S[i]
    return best if best > 0 else 1.0


def _ad_rows(n_total: int) -> np.ndarray:
    """A handful of rows per block (start, middle, end) for the cheap AD check inside the objective.

    kNN queries dominate the run time, so the objective checks these rows and the final report
    checks every row; the reported ``ad_report`` is therefore the authoritative one.
    """
    idx: list[int] = []
    start = 0
    for d in DURATIONS_S:
        n = round(d * HZ)
        idx += [start + 2, start + n // 2, start + n - 1]
        start += n
    return np.array([i for i in idx if i < n_total], dtype=int)


def _trajectory(
    theta: np.ndarray, model: TrajectoryModel, drive_map: DriveMap, coolant: float, ambient: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drive-mapped model inputs (with a profile id) and the model's predicted trajectories."""
    cyc = blocks(subject_params(theta, coolant, ambient))
    x = drive_map.to_inputs(cyc["torque"].to_numpy(), cyc["motor_speed"].to_numpy(), coolant, ambient)
    x["profile_id"] = 0
    return x, model.predict(x)


def optimize(
    variant: Literal["O1", "O2", "O3"],
    model: TrajectoryModel,
    conformal: Any,
    ad: ApplicabilityDomain,
    drive_map: DriveMap,
    limits: Mapping[str, float],
    bounds: Sequence[tuple[float, float]],
    seed: int = 0,
    *,
    coolant: float = COOLANT_C,
    ambient: float = AMBIENT_C,
    popsize: int = 15,
    maxiter: int = 50,
) -> OptResult:
    """Solve one variant with seeded ``differential_evolution`` (``polish=False``, one worker)."""
    if variant not in ("O1", "O2", "O3"):
        raise ValueError(f"unknown variant {variant!r}")
    if len(bounds) != 6:
        raise ValueError("bounds must have 6 entries: (torque, speed) for each of 3 blocks")
    targets = [t for t in model.targets if t in LIMIT_KEYS]
    missing = [LIMIT_KEYS[t] for t in targets if LIMIT_KEYS[t] not in limits]
    if not targets or missing:
        raise ValueError(f"missing limits {missing or list(LIMIT_KEYS.values())}")  # fail closed
    cls = length_class(sum(DURATIONS_S))
    e_scale = _energy_scale(bounds)
    rows = _ad_rows(round(sum(DURATIONS_S) * HZ))

    def evaluate(theta: np.ndarray) -> tuple[dict[str, float], dict[str, float | None], pd.DataFrame]:
        x, pred = _trajectory(theta, model, drive_map, coolant, ambient)
        pk = {t: float(pred[t].max()) for t in targets}
        up: dict[str, float | None] = {}
        for t in targets:
            iv = conformal.interval(t, pk[t], cls)
            up[t] = None if iv is None else float(iv[1])
        return pk, up, x

    def objective(theta: np.ndarray) -> float:
        pk, up, x = evaluate(theta)
        cost = -energy_J(theta) / e_scale
        violation = 0.0
        for t in targets:
            lim = float(limits[LIMIT_KEYS[t]])
            if variant == "O1":
                violation += max(0.0, pk[t] - lim) / 10.0
            else:
                u = up[t]
                violation += _INFEASIBLE if u is None else max(0.0, u - lim) / 10.0
        if variant == "O3" and violation == 0.0:  # kNN is slow: only pay for it on thermally feasible points
            feats = model.features(x)[model.feature_names].to_numpy(dtype=float)
            rep = ad.check(feats[rows])
            violation += rep.frac_outside
            violation += max(0.0, rep.max_knn_distance - rep.threshold) / max(rep.threshold, 1e-9)
        return cost + _PENALTY * violation

    res = differential_evolution(
        objective,
        list(bounds),
        seed=seed,
        polish=False,
        maxiter=maxiter,
        popsize=popsize,
        workers=1,
        updating="immediate",
    )
    theta = np.asarray(res.x, dtype=float)
    pk, up, x = evaluate(theta)
    # Headline numbers are for the first target (pm for the default model).
    head = targets[0]
    feats = model.features(x)[model.feature_names].to_numpy(dtype=float)
    return OptResult(
        theta=theta,
        subject_params=subject_params(theta, coolant, ambient),
        pred_peak=pk[head],
        upper=up[head],
        ad_report=ad.check(feats),
    )
