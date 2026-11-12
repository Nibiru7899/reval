"""Virtual world: a 7-node thermal network, structurally different from the design-time LPTN.

Differences from ``motor.lptn`` (4 nodes): rotor core, end winding and housing are extra nodes; the
air-gap, end-winding-air, winding-tooth, tooth-yoke and housing-coolant conductances depend on speed
and temperature; the flow-conductance relation is a saturating law ``G ~ s (1 + k) / (s + k)`` rather
than the LPTN's flow^0.8 power law; losses use different functional forms. A smooth speed-dependent
loss term (``model_form_error_w``) that the design model cannot represent is injected on purpose.

Units: temperatures degC absolute; G in W/K; C in J/K; losses W; speed rpm; currents A; voltages V.
Everything here is deterministic; noise enters only through the ``rng`` given to ``World.measure``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

NODES: tuple[str, ...] = (
    "pm",
    "rotor_core",
    "stator_tooth",
    "stator_yoke",
    "stator_winding",
    "end_winding",
    "housing",
)
OBSERVED: tuple[str, ...] = ("pm", "stator_yoke", "stator_tooth", "stator_winding")
_PM, _RC, _ST, _SY, _SW, _EW, _HS = range(7)
_OBS_IDX = [NODES.index(n) for n in OBSERVED]

C_NAMES = tuple(f"C_{n}" for n in NODES)
G_NAMES: tuple[str, ...] = (
    "G_pm_rc",
    "G_airgap",
    "G_sw_st",
    "G_sw_ew",
    "G_ew_air",
    "G_ew_hs",
    "G_st_sy",
    "G_sy_hs",
    "G_hs_cool",
    "G_rc_amb",
)
LOSS_NAMES: tuple[str, ...] = ("k_cu", "k_hyst", "k_eddy", "k_pm", "k_rc")
FIT_NAMES: tuple[str, ...] = (*C_NAMES, *G_NAMES, *LOSS_NAMES)

_ALPHA_CU = 0.00393  # material constant, not fitted
_EW_COPPER_SHARE = 0.3
_FE_TOOTH_SHARE = 0.55
_FLOW_K = 1.0  # saturation constant of the flow law
_V_SCALE = 100.0
_W_SCALE = 1000.0

DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    **{n: (1.0e3, 2.0e5) for n in C_NAMES},
    **{n: (0.05, 500.0) for n in G_NAMES},
    "k_cu": (1.0e-4, 1.0),
    "k_hyst": (1.0e-2, 1.0e3),
    "k_eddy": (1.0e-3, 1.0e3),
    "k_pm": (1.0e-2, 1.0e3),
    "k_rc": (1.0e-2, 1.0e3),
}


@dataclass(frozen=True)
class PhysicalParams:
    """Physical changes applied to the plant (Tier B). Neutral values mean "as calibrated"."""

    R_ic_scale: float = 1.0  # scales the yoke-housing interface resistance
    coolant_flow_scale: float = 1.0  # relative coolant flow (1.0 = bench condition)
    sensor_offset: float = 0.0  # K, added to the pm sensor reading only (measure(), not the state)

    def __post_init__(self) -> None:
        if self.R_ic_scale <= 0.0 or self.coolant_flow_scale <= 0.0:
            raise ValueError("R_ic_scale and coolant_flow_scale must be positive")


@dataclass(frozen=True)
class WorldParams:
    """Calibrated world parameters, keyed by ``FIT_NAMES``, plus the injected model-form error."""

    values: Mapping[str, float]
    model_form_error_w: float = 40.0  # peak extra heating in W (smooth bump around 3 krpm)
    sigma_sensor_k: float = 0.5  # K, std of additive sensor noise


@dataclass(frozen=True)
class Drive:
    """Per-step input arrays of shape (T, B), zero-order hold over each step."""

    i_s: np.ndarray
    u_s: np.ndarray
    w: np.ndarray
    t_c: np.ndarray
    t_a: np.ndarray


def default_world_params() -> WorldParams:
    """Order-of-magnitude starting point for calibration (not a fitted world)."""
    c = [1.5e4, 2.0e4, 3.0e3, 1.0e4, 3.0e3, 2.0e3, 2.0e4]
    g = [15.0, 8.0, 50.0, 30.0, 1.5, 3.0, 60.0, 70.0, 80.0, 0.5]
    loss = [0.03, 80.0, 0.5, 8.0, 5.0]
    vals = [*c, *g, *loss]
    return WorldParams(values=dict(zip(FIT_NAMES, vals, strict=True)))


def flow_factor(s: float) -> float:
    """Saturating flow-conductance relation, equal to 1 at ``s = 1`` (not the LPTN's power law)."""
    return s * (1.0 + _FLOW_K) / (s + _FLOW_K)


def drive_from_frame(df: pd.DataFrame) -> Drive:
    """Single-profile drive (B = 1) from a frame with the dataset's input columns."""
    i_s = np.hypot(df["i_d"].to_numpy(float), df["i_q"].to_numpy(float))
    u_s = np.hypot(df["u_d"].to_numpy(float), df["u_q"].to_numpy(float))
    cols = (
        i_s,
        u_s,
        df["motor_speed"].to_numpy(float),
        df["coolant"].to_numpy(float),
        df["ambient"].to_numpy(float),
    )
    return Drive(*(c[:, None] for c in cols))


def stability_substeps(v: Mapping[str, float], phys: PhysicalParams, dt: float) -> int:
    """Euler sub-steps per ``dt`` so each is below half the fastest nodal time constant.

    Conductances use worst-case (6 krpm, hot) multipliers so the guard holds for any drive in the
    dataset envelope and for any parameter vector proposed by the optimiser.
    """
    g_ag = v["G_airgap"] * 3.2
    g_sw_st, g_sw_ew = v["G_sw_st"] * 1.15, v["G_sw_ew"]
    g_ew_air, g_ew_hs = v["G_ew_air"] * 4.7, v["G_ew_hs"]
    g_st_sy, g_sy_hs = v["G_st_sy"] * 1.1, v["G_sy_hs"] / phys.R_ic_scale
    g_hc = v["G_hs_cool"] * flow_factor(phys.coolant_flow_scale) * 1.3
    sums = [
        v["G_pm_rc"],
        v["G_pm_rc"] + g_ag + v["G_rc_amb"],
        g_ag + g_sw_st + g_st_sy,
        g_st_sy + g_sy_hs,
        g_sw_st + g_sw_ew,
        g_sw_ew + g_ew_air + g_ew_hs,
        g_sy_hs + g_ew_hs + g_hc,
    ]
    tau = min(v[c] / s for c, s in zip(C_NAMES, sums, strict=True))
    return min(400, max(1, math.ceil(dt / (0.5 * tau))))


def integrate(
    drive: Drive,
    theta0: np.ndarray,
    dt: float,
    v: Mapping[str, float],
    phys: PhysicalParams,
    err_w: float,
    n_sub: int,
) -> np.ndarray:
    """Euler-integrate B independent profiles. ``theta0`` is (7, B); returns (T + 1, 7, B)."""
    n_steps, n_b = drive.i_s.shape
    h = dt / n_sub
    inv_c = np.array([h / v[c] for c in C_NAMES])[:, None]
    wk = drive.w / _W_SCALE
    awk = np.abs(wk)
    uk = drive.u_s / _V_SCALE
    ik = drive.i_s / 100.0
    cu0 = v["k_cu"] * drive.i_s**2
    p_fe = v["k_hyst"] * awk**1.2 + v["k_eddy"] * wk**2 * (1.0 + 0.5 * uk)
    p_pm = v["k_pm"] * wk**2 * ik**2
    p_rc = v["k_rc"] * awk * ik**2
    p_err = err_w * np.exp(-(((awk - 3.0) / 1.5) ** 2))  # smooth in speed, peak at 3 krpm
    g_ag = v["G_airgap"] * (1.0 + 0.35 * awk)
    g_ew_air = v["G_ew_air"] * (1.0 + 0.6 * awk)
    g_hc = v["G_hs_cool"] * flow_factor(phys.coolant_flow_scale) * (1.0 + 0.004 * (drive.t_c - 40.0))
    g_pm_rc, g_sw_ew, g_ew_hs = v["G_pm_rc"], v["G_sw_ew"], v["G_ew_hs"]
    g_sy_hs, g_rc_amb = v["G_sy_hs"] / phys.R_ic_scale, v["G_rc_amb"]
    g_sw_st0, g_st_sy0 = v["G_sw_st"], v["G_st_sy"]

    out = np.empty((n_steps + 1, 7, n_b))
    th = theta0.astype(float).copy()
    out[0] = th
    src = np.empty((7, n_b))
    for k in range(n_steps):
        tc, ta = drive.t_c[k], drive.t_a[k]
        for _ in range(n_sub):
            pm, rc, st, sy, sw, ew, hs = th
            g_sw_st = g_sw_st0 * (1.0 + 0.002 * (sw - 80.0))
            g_st_sy = g_st_sy0 * (1.0 - 0.0012 * (st - 60.0))
            cu = cu0[k] * (1.0 + _ALPHA_CU * (sw - 20.0))
            q_pm_rc = g_pm_rc * (pm - rc)
            q_rc_st = g_ag[k] * (rc - st)
            q_sw_st = g_sw_st * (sw - st)
            q_sw_ew = g_sw_ew * (sw - ew)
            q_st_sy = g_st_sy * (st - sy)
            q_sy_hs = g_sy_hs * (sy - hs)
            q_ew_hs = g_ew_hs * (ew - hs)
            src[_PM] = p_pm[k] + 0.4 * p_err[k] - q_pm_rc
            src[_RC] = p_rc[k] + 0.6 * p_err[k] + q_pm_rc - q_rc_st + g_rc_amb * (ta - rc)
            src[_ST] = _FE_TOOTH_SHARE * p_fe[k] + q_rc_st + q_sw_st - q_st_sy
            src[_SY] = (1.0 - _FE_TOOTH_SHARE) * p_fe[k] + q_st_sy - q_sy_hs
            src[_SW] = (1.0 - _EW_COPPER_SHARE) * cu - q_sw_st - q_sw_ew
            src[_EW] = _EW_COPPER_SHARE * cu + q_sw_ew + g_ew_air[k] * (ta - ew) - q_ew_hs
            src[_HS] = q_sy_hs + q_ew_hs + g_hc[k] * (tc - hs)
            th = th + inv_c * src
        out[k + 1] = th
    return out


def initial_state(trajectory: pd.DataFrame) -> np.ndarray:
    """Seven-node initial state: observed nodes from the first row (coolant if absent); the rotor
    core starts at the pm temperature, the end winding at the winding's, the housing at the yoke's."""
    first = trajectory.iloc[0]
    t0 = float(first["coolant"])
    g = {n: float(first[n]) if n in trajectory.columns else t0 for n in OBSERVED}
    return np.array(
        [
            g["pm"],
            g["pm"],
            g["stator_tooth"],
            g["stator_yoke"],
            g["stator_winding"],
            g["stator_winding"],
            g["stator_yoke"],
        ]
    )


@dataclass(frozen=True)
class World:
    """The simulated plant. Construct from calibrated ``WorldParams``."""

    params: WorldParams = field(default_factory=default_world_params)

    def simulate(
        self, trajectory: pd.DataFrame, physical_params: PhysicalParams | None = None, dt: float = 0.5
    ) -> pd.DataFrame:
        """Noise-free observed temperatures (``OBSERVED`` columns, index of ``trajectory``).

        ``trajectory`` needs i_d, i_q, u_d, u_q, motor_speed, coolant, ambient at ``dt`` spacing. Row t
        is the state before input row t acts (as in ``motor.lptn.simulate``), so row 0 is the initial state.
        """
        phys = physical_params or PhysicalParams()
        if len(trajectory) == 0:
            return pd.DataFrame(columns=list(OBSERVED), index=trajectory.index, dtype=float)
        n_sub = stability_substeps(self.params.values, phys, dt)
        traj = integrate(
            drive_from_frame(trajectory),
            initial_state(trajectory)[:, None],
            dt,
            self.params.values,
            phys,
            self.params.model_form_error_w,
            n_sub,
        )
        return pd.DataFrame(
            traj[: len(trajectory), _OBS_IDX, 0], columns=list(OBSERVED), index=trajectory.index
        )

    def measure(
        self, trajectory: pd.DataFrame, physical_params: PhysicalParams | None, rng: np.random.Generator
    ) -> pd.DataFrame:
        """``simulate`` plus the pm sensor offset plus ``N(0, sigma_sensor)`` noise on every column."""
        phys = physical_params or PhysicalParams()
        out = self.simulate(trajectory, phys) + rng.normal(
            0.0, self.params.sigma_sensor_k, size=(len(trajectory), 4)
        )
        out["pm"] = out["pm"] + phys.sensor_offset
        return out
