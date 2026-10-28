"""Independent physics model: a 4-node lumped-parameter thermal network (LPTN) of the PMSM.

Units (everywhere in this module):
    temperatures  degC, absolute          losses  W
    R             K/W                     C       J/K
    i_s           A (hypot(i_d, i_q))     u_s     V (hypot(u_d, u_q))
    w             rpm (``motor_speed``)   dt      s

Nodes: PM (rotor magnet), stator yoke (SY), stator tooth (ST), stator winding (SW).
Boundaries: coolant and ambient temperature. Heat paths (see docs/05 section 4):
SW-ST, ST-SY, SY-coolant (the only flow-dependent resistance), PM-ST, PM-ambient, SW-ambient.

Integration is explicit Euler. ``simulate`` is the public, strict entry point and raises when ``dt``
violates the stability guard. ``identify`` integrates at a coarse dt (10 s) and therefore *sub-steps
internally* (zero-order-hold inputs) so that every sub-step satisfies the same guard; it never raises
for a parameter vector the optimiser proposes.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.optimize import least_squares

NODES: tuple[str, ...] = ("pm", "stator_yoke", "stator_tooth", "stator_winding")

_PM, _SY, _ST, _SW = NODES

# R pairs -> short key used in the YAML pointer space (/R/sw_st, ...).
R_KEYS: dict[tuple[str, str], str] = {
    (_SW, _ST): "sw_st",
    (_ST, _SY): "st_sy",
    (_SY, "coolant"): "sy_c",
    (_PM, _ST): "pm_st",
    (_PM, "ambient"): "pm_amb",
    (_SW, "ambient"): "sw_amb",
}
C_KEYS: dict[str, str] = {_PM: "pm", _SY: "sy", _ST: "st", _SW: "sw"}
LOSS_KEYS: tuple[str, ...] = ("k_cu", "alpha_cu", "k_fe1", "k_fe2", "k_pm")

# Speed and voltage are normalised inside ``losses`` so that the loss coefficients are O(1e-3..1e0)
# and the log-parameter optimisation is well conditioned.
_W_SCALE = 1000.0
_U_SCALE = 100.0
_I_SCALE = 100.0
_THETA_REF_CU = 20.0  # degC, reference temperature of the copper-loss law
_FE_SPLIT_ST = 0.5  # iron loss share going to the tooth; the rest goes to the yoke (not identifiable apart)

# Fitted (log-)parameters, in vector order. alpha_cu is a material constant and stays fixed.
_FIT_KEYS: tuple[str, ...] = (
    *(f"/C/{k}" for k in C_KEYS.values()),
    *(f"/R/{k}" for k in R_KEYS.values()),
    "/loss/k_cu",
    "/loss/k_fe1",
    "/loss/k_fe2",
    "/loss/k_pm",
)

DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    **{f"/C/{k}": (1.0e3, 1.0e6) for k in C_KEYS.values()},
    **{f"/R/{k}": (1.0e-2, 5.0) for k in R_KEYS.values()},
    "/loss/k_cu": (1.0e-5, 1.0),
    "/loss/k_fe1": (1.0e-3, 1.0e3),
    "/loss/k_fe2": (1.0e-3, 1.0e3),
    "/loss/k_pm": (1.0e-3, 1.0e3),
}


@dataclass(frozen=True)
class LPTNParams:
    """Network parameters. ``R`` keys are node pairs (see ``R_KEYS``); ``C`` keys are ``NODES``."""

    C: dict[str, float]
    R: dict[tuple[str, str], float]
    k_cu: float
    alpha_cu: float
    k_fe1: float
    k_fe2: float
    k_pm: float


def default_params() -> LPTNParams:
    """Order-of-magnitude initial guess for a 50 kW-class automotive PMSM."""
    return LPTNParams(
        C={_PM: 1.0e4, _SY: 2.0e4, _ST: 1.0e4, _SW: 5.0e3},
        R={
            (_SW, _ST): 0.05,
            (_ST, _SY): 0.04,
            (_SY, "coolant"): 0.04,
            (_PM, _ST): 0.2,
            (_PM, "ambient"): 1.0,
            (_SW, "ambient"): 1.0,
        },
        k_cu=5.0e-3,
        alpha_cu=0.00393,
        k_fe1=0.2,
        k_fe2=0.2,
        k_pm=0.2,
    )


def r_coolant(r_ic_nominal: float, flow_scale: float) -> float:
    """Coolant-side resistance for a relative flow ``flow_scale`` (1.0 = test-bench condition).

    ``R_ic = R_ic,nominal * flow_scale ** -0.8``: for turbulent forced convection Nu ~ Re^0.8
    (Dittus-Boelter; e.g. Incropera and DeWitt, *Fundamentals of Heat and Mass Transfer*, ch. 8), so the
    convective conductance scales with flow^0.8.
    """
    if flow_scale <= 0.0:
        raise ValueError("flow_scale must be positive")
    return r_ic_nominal * flow_scale**-0.8


def losses(
    i_s: np.ndarray, u_s: np.ndarray, w: np.ndarray, theta_sw: np.ndarray, p: LPTNParams
) -> dict[str, np.ndarray]:
    """Loss power per node in W.

    Copper (SW): ``k_cu * i_s^2 * (1 + alpha_cu * (theta_sw - 20))``.
    Iron (ST and SY, split evenly): ``k_fe1 * |w| + k_fe2 * w^2 * u_s`` with w in krpm and u_s in 100 V.
    Magnet (PM): ``k_pm * w^2 * i_s^2`` with w in krpm and i_s in 100 A (eddy losses grow with the
    stator-current harmonics as well as with frequency).
    """
    i_s, u_s, w, theta_sw = (np.asarray(a, dtype=float) for a in (i_s, u_s, w, theta_sw))
    wk = w / _W_SCALE
    uk = u_s / _U_SCALE
    p_cu = p.k_cu * i_s**2 * (1.0 + p.alpha_cu * (theta_sw - _THETA_REF_CU))
    p_fe = p.k_fe1 * np.abs(wk) + p.k_fe2 * wk**2 * uk
    return {
        _SW: p_cu,
        _ST: _FE_SPLIT_ST * p_fe,
        _SY: (1.0 - _FE_SPLIT_ST) * p_fe,
        _PM: p.k_pm * wk**2 * (i_s / _I_SCALE) ** 2,
    }


def _node_time_constants(p: LPTNParams, flow_scale: float) -> dict[str, float]:
    g = _conductances(p, flow_scale)
    return {
        _PM: p.C[_PM] / (g["pm_st"] + g["pm_amb"]),
        _SY: p.C[_SY] / (g["st_sy"] + g["sy_c"]),
        _ST: p.C[_ST] / (g["sw_st"] + g["st_sy"] + g["pm_st"]),
        _SW: p.C[_SW] / (g["sw_st"] + g["sw_amb"]),
    }


def stability_limit(p: LPTNParams, flow_scale: float = 1.0) -> float:
    """Largest allowed Euler step in s: half of the fastest nodal time constant ``C_i / sum_j(1/R_ij)``.

    The nodal constant never exceeds any single ``R*C`` product, so this is at least as strict as the
    ``min(R*C)/2`` rule in the task spec, and it is the true explicit-Euler stability scale (dt < 2*tau).
    """
    return min(_node_time_constants(p, flow_scale).values()) / 2.0


def _conductances(p: LPTNParams, flow_scale: float) -> dict[str, float]:
    r = {name: p.R[pair] for pair, name in R_KEYS.items()}
    r["sy_c"] = r_coolant(r["sy_c"], flow_scale)
    return {k: 1.0 / v for k, v in r.items()}


def _integrate(
    i_s: np.ndarray,
    u_s: np.ndarray,
    w: np.ndarray,
    t_c: np.ndarray,
    t_a: np.ndarray,
    theta0: np.ndarray,
    dt: float,
    p: LPTNParams,
    flow_scale: float,
    n_sub: int,
) -> np.ndarray:
    """Euler-integrate B independent profiles at once.

    Inputs have shape (T, B) and are held constant over each step (zero-order hold). ``theta0`` has shape
    (4, B) in ``NODES`` order. Returns shape (T + 1, 4, B): row k is the state *before* applying input k.
    """
    n_steps, n_batch = i_s.shape
    g = _conductances(p, flow_scale)
    g_sw_st, g_st_sy, g_sy_c = g["sw_st"], g["st_sy"], g["sy_c"]
    g_pm_st, g_pm_a, g_sw_a = g["pm_st"], g["pm_amb"], g["sw_amb"]
    h = dt / n_sub
    ih_pm, ih_sy = h / p.C[_PM], h / p.C[_SY]
    ih_st, ih_sw = h / p.C[_ST], h / p.C[_SW]
    ref = _THETA_REF_CU

    wk = w / _W_SCALE
    uk = u_s / _U_SCALE
    p_fe = p.k_fe1 * np.abs(wk) + p.k_fe2 * wk**2 * uk
    p_fe_st = _FE_SPLIT_ST * p_fe
    p_fe_sy = (1.0 - _FE_SPLIT_ST) * p_fe
    p_pm = p.k_pm * wk**2 * (i_s / _I_SCALE) ** 2
    cu0 = p.k_cu * i_s**2
    acu = p.alpha_cu

    out = np.empty((n_steps + 1, 4, n_batch))
    pm, sy, st, sw = (theta0[i].astype(float).copy() for i in range(4))
    out[0] = np.stack([pm, sy, st, sw])
    for k in range(n_steps):
        tc, ta = t_c[k], t_a[k]
        c0, f_st, f_sy, f_pm = cu0[k], p_fe_st[k], p_fe_sy[k], p_pm[k]
        for _ in range(n_sub):
            q_sw_st = g_sw_st * (sw - st)
            q_st_sy = g_st_sy * (st - sy)
            q_pm_st = g_pm_st * (pm - st)
            d_pm = f_pm - q_pm_st + g_pm_a * (ta - pm)
            d_sy = f_sy + q_st_sy + g_sy_c * (tc - sy)
            d_st = f_st + q_sw_st + q_pm_st - q_st_sy
            d_sw = c0 * (1.0 + acu * (sw - ref)) - q_sw_st + g_sw_a * (ta - sw)
            pm = pm + ih_pm * d_pm
            sy = sy + ih_sy * d_sy
            st = st + ih_st * d_st
            sw = sw + ih_sw * d_sw
        out[k + 1] = np.stack([pm, sy, st, sw])
    return out


def _drive_arrays(inputs: pd.DataFrame) -> tuple[np.ndarray, ...]:
    """(i_s, u_s, w, coolant, ambient) as float arrays; i_s and u_s are computed locally."""
    i_s = np.hypot(inputs["i_d"].to_numpy(float), inputs["i_q"].to_numpy(float))
    u_s = np.hypot(inputs["u_d"].to_numpy(float), inputs["u_q"].to_numpy(float))
    return (
        i_s,
        u_s,
        inputs["motor_speed"].to_numpy(float),
        inputs["coolant"].to_numpy(float),
        inputs["ambient"].to_numpy(float),
    )


def simulate(
    inputs: pd.DataFrame,
    p: LPTNParams,
    theta0: Mapping[str, float] | None = None,
    dt: float = 0.5,
    *,
    flow_scale: float = 1.0,
) -> pd.DataFrame:
    """Simulate one profile with explicit Euler; columns are ``NODES``, index matches ``inputs``.

    Row t holds the node temperatures *before* input row t acts (so row 0 is ``theta0``). ``theta0``
    defaults to the coolant temperature at t = 0 for every node. Raises ``ValueError`` when ``dt`` exceeds
    the stability guard (``stability_limit``).
    """
    limit = stability_limit(p, flow_scale)
    if dt > limit:
        raise ValueError(f"dt={dt} s exceeds the explicit-Euler stability limit {limit:.4g} s")
    i_s, u_s, w, t_c, t_a = _drive_arrays(inputs)
    if len(inputs) == 0:
        return pd.DataFrame(columns=list(NODES), index=inputs.index, dtype=float)
    start = np.array([[(theta0 or {}).get(n, t_c[0])] for n in NODES], dtype=float)
    traj = _integrate(
        i_s[:, None], u_s[:, None], w[:, None], t_c[:, None], t_a[:, None], start, dt, p, flow_scale, 1
    )
    return pd.DataFrame(traj[: len(inputs), :, 0], columns=list(NODES), index=inputs.index)


# --------------------------------------------------------------------------------------------------
# Parameter (de)serialisation
# --------------------------------------------------------------------------------------------------


def _to_flat(p: LPTNParams) -> dict[str, float]:
    flat: dict[str, float] = {f"/C/{C_KEYS[n]}": p.C[n] for n in NODES}
    flat.update({f"/R/{name}": p.R[pair] for pair, name in R_KEYS.items()})
    flat.update({f"/loss/{k}": getattr(p, k) for k in LOSS_KEYS})
    return flat


def _from_flat(flat: Mapping[str, float]) -> LPTNParams:
    return LPTNParams(
        C={n: float(flat[f"/C/{C_KEYS[n]}"]) for n in NODES},
        R={pair: float(flat[f"/R/{name}"]) for pair, name in R_KEYS.items()},
        **{k: float(flat[f"/loss/{k}"]) for k in LOSS_KEYS},
    )


def dump_params(p: LPTNParams, path: Path) -> None:
    """Write nested YAML whose JSON pointers are /R/sw_st, /C/pm, /loss/k_cu, ... (manifest-friendly)."""
    doc: dict[str, dict[str, float]] = {"C": {}, "R": {}, "loss": {}}
    for key, value in _to_flat(p).items():
        _, group, name = key.split("/")
        doc[group][name] = float(value)
    header = (
        "# LPTN parameters. Units: C in J/K, R in K/W, k_cu in W/A^2, alpha_cu in 1/K.\n"
        "# Iron/magnet loss coefficients use w in krpm, u_s in 100 V, i_s in 100 A (see motor/lptn.py).\n"
        "# Generated by scripts/calibrate_lptn.py. Do not hand-edit fitted values.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def load_params(path: Path) -> LPTNParams:
    """Inverse of ``dump_params``."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    flat = {f"/{g}/{k}": v for g, grp in doc.items() for k, v in grp.items()}
    return _from_flat(flat)


# --------------------------------------------------------------------------------------------------
# Identification
# --------------------------------------------------------------------------------------------------

_STEP_S = 10.0  # identification time step (s); 20 samples at 2 Hz
_MAX_SUB = 400  # sub-step cap; with the default bounds the cap is never reached


def _resample_profile(g: pd.DataFrame, stride: int) -> tuple[np.ndarray, ...] | None:
    """Block means of the inputs over ``stride`` rows and node temperatures at the block boundaries."""
    n_blocks = (len(g) - 1) // stride
    if n_blocks < 2:
        return None
    n = n_blocks * stride
    drive = _drive_arrays(g.iloc[:n])
    blocks = [a.reshape(n_blocks, stride).mean(axis=1) for a in drive]
    temps = g[list(NODES)].to_numpy(float)[: n + 1 : stride]  # (n_blocks + 1, 4)
    return (*blocks, temps)


def _pack(frame: pd.DataFrame, ids: list[int], stride: int) -> dict[str, np.ndarray]:
    """Pad resampled profiles to a common length; ``mask`` marks real (non-padded) samples."""
    parts = []
    for pid in ids:
        r = _resample_profile(frame[frame["profile_id"] == pid], stride)
        if r is not None:
            parts.append(r)
    if not parts:
        raise ValueError("no usable profiles (need at least 2 resampled blocks each)")
    t_max = max(len(r[0]) for r in parts)
    n_b = len(parts)
    drive = [np.zeros((t_max, n_b)) for _ in range(5)]
    temps = np.zeros((t_max + 1, 4, n_b))
    mask = np.zeros((t_max + 1, n_b), dtype=bool)
    for b, r in enumerate(parts):
        n_blocks = len(r[0])
        for j in range(5):
            drive[j][:n_blocks, b] = r[j]
            drive[j][n_blocks:, b] = r[j][-1]
        temps[: n_blocks + 1, :, b] = r[5]
        temps[n_blocks + 1 :, :, b] = r[5][-1]
        mask[: n_blocks + 1, b] = True
    return {
        "i_s": drive[0],
        "u_s": drive[1],
        "w": drive[2],
        "t_c": drive[3],
        "t_a": drive[4],
        "temps": temps,
        "mask": mask,
    }


def _simulate_packed(p: LPTNParams, data: dict[str, np.ndarray], dt: float) -> np.ndarray:
    """Simulate packed profiles, sub-stepping so each sub-step respects the stability guard."""
    limit = stability_limit(p, 1.0)
    n_sub = min(_MAX_SUB, max(1, math.ceil(dt / limit)))
    return _integrate(
        data["i_s"],
        data["u_s"],
        data["w"],
        data["t_c"],
        data["t_a"],
        data["temps"][0],
        dt,
        p,
        1.0,
        n_sub,
    )


def _vector_to_params(x: np.ndarray, template: LPTNParams) -> LPTNParams:
    flat = _to_flat(template)
    flat.update({k: float(math.exp(v)) for k, v in zip(_FIT_KEYS, x, strict=True)})
    return _from_flat(flat)


def _per_node_mse(sim: np.ndarray, data: dict[str, np.ndarray]) -> dict[str, float]:
    mask = data["mask"]
    err = sim - data["temps"]  # (T+1, 4, B)
    out: dict[str, float] = {}
    for i, n in enumerate(NODES):
        e = err[:, i, :][mask]
        out[n] = float(np.mean(e**2)) if e.size else float("nan")
    return out


def identify(
    df_train: pd.DataFrame,
    p0: LPTNParams,
    bounds: Mapping[str, tuple[float, float]],
    max_profiles: int | None = None,
    seed: int = 0,
    *,
    max_nfev: int = 80,
) -> tuple[LPTNParams, dict[str, Any]]:
    """Fit C, R and the loss coefficients to ``df_train`` with ``scipy.optimize.least_squares``.

    The optimisation runs on log-parameters (positivity) with box ``bounds`` keyed like ``DEFAULT_BOUNDS``
    ("/R/sw_st", ...); missing keys fall back to ``DEFAULT_BOUNDS``. Each profile is resampled to 10 s
    block means of the inputs and simulated from its measured initial node temperatures at dt = 10 s with
    internal sub-stepping (stability guard). Residuals are simulated minus measured temperature (K) at
    all four nodes. ``alpha_cu`` is a material constant and is kept at ``p0.alpha_cu``. Profiles are chosen
    deterministically from ``seed`` when ``max_profiles`` is set. Returns the fitted parameters and an
    info dict (per-node MSE in K^2 on the fitted subsample, nfev, runtime, profiles used, ...).
    """
    started = time.perf_counter()
    all_ids = sorted(int(i) for i in df_train["profile_id"].unique())
    ids = all_ids
    if max_profiles is not None and max_profiles < len(all_ids):
        rng = np.random.default_rng(seed)
        ids = sorted(int(i) for i in rng.choice(all_ids, size=max_profiles, replace=False))
    stride = max(1, round(_STEP_S / 0.5))
    data = _pack(df_train[df_train["profile_id"].isin(ids)], ids, stride)

    lo = np.array([math.log(bounds.get(k, DEFAULT_BOUNDS[k])[0]) for k in _FIT_KEYS])
    hi = np.array([math.log(bounds.get(k, DEFAULT_BOUNDS[k])[1]) for k in _FIT_KEYS])
    flat0 = _to_flat(p0)
    x0 = np.clip(np.log([flat0[k] for k in _FIT_KEYS]), lo + 1e-9, hi - 1e-9)
    mask = data["mask"]

    def residuals(x: np.ndarray) -> np.ndarray:
        sim = _simulate_packed(_vector_to_params(x, p0), data, _STEP_S)
        res = (sim - data["temps"]).transpose(0, 2, 1)[mask]
        return np.nan_to_num(res.ravel(), nan=1.0e3, posinf=1.0e3, neginf=-1.0e3)

    sol = least_squares(
        residuals, x0, bounds=(lo, hi), method="trf", x_scale="jac", diff_step=1e-3, max_nfev=max_nfev
    )
    fitted = _vector_to_params(sol.x, p0)
    sim = _simulate_packed(fitted, data, _STEP_S)
    n_sub = min(_MAX_SUB, max(1, math.ceil(_STEP_S / stability_limit(fitted, 1.0))))
    at_bound = [
        k for k, v, a, b in zip(_FIT_KEYS, sol.x, lo, hi, strict=True) if v - a < 1e-3 or b - v < 1e-3
    ]
    info: dict[str, Any] = {
        "mse_train": _per_node_mse(sim, data),
        "cost": float(sol.cost),
        "nfev": int(sol.nfev),
        "success": bool(sol.success),
        "status": int(sol.status),
        "message": str(sol.message),
        "profiles": ids,
        "n_samples": int(mask.sum()),
        "dt_identify_s": _STEP_S,
        "n_substeps": n_sub,
        "params_at_bound": at_bound,
        "runtime_s": time.perf_counter() - started,
    }
    return replace(fitted), info


def evaluate_mse(p: LPTNParams, df: pd.DataFrame, *, stride: int = 20) -> dict[str, float]:
    """Per-node MSE in K^2 of the 10 s (default) resimulation against measured temperatures on ``df``."""
    ids = sorted(int(i) for i in df["profile_id"].unique())
    data = _pack(df, ids, stride)
    return _per_node_mse(_simulate_packed(p, data, stride * 0.5), data)


def _window_peaks(values: np.ndarray, window_rows: int) -> np.ndarray:
    n = len(values) // window_rows
    if n == 0:
        return np.empty(0)
    return values[: n * window_rows].reshape(n, window_rows).max(axis=1)


def model_form_band(p: LPTNParams, df_test: pd.DataFrame, window_rows: int) -> dict[str, float]:
    """Per node: 95th percentile of |peak_sim - peak_true| (K) over non-overlapping windows.

    Each profile is simulated at dt = 0.5 s from its measured initial node temperatures; windows are
    ``window_rows`` rows long, per profile, and a trailing partial window is dropped.
    """
    diffs: dict[str, list[np.ndarray]] = {n: [] for n in NODES}
    for _, g in df_test.groupby("profile_id", sort=True):
        sim = simulate(g, p, theta0={n: float(g[n].iloc[0]) for n in NODES})
        for n in NODES:
            ps = _window_peaks(sim[n].to_numpy(), window_rows)
            pt = _window_peaks(g[n].to_numpy(float), window_rows)
            diffs[n].append(np.abs(ps - pt))
    band: dict[str, float] = {}
    for n in NODES:
        d = np.concatenate(diffs[n]) if diffs[n] else np.empty(0)
        band[n] = float(np.quantile(d, 0.95)) if d.size else float("nan")
    return band
