"""Evidence producers for the motor example (docs/10 section 12; ML producers arrive in P4-03).

Producer ids are the binding names: ``lptn_sim``, ``bench_measure``, ``shaft_check``, ``current_limit_check``.
Every artifact a producer touches is declared in ``depends_on`` (fail closed: reading anything else raises).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

import reval
from motor import cycles, lptn
from motor.features import add_derived
from reval.domain.engineering import Subject, SubjectKind
from reval.domain.evidence import EvidenceResult, Tolerance
from reval.errors import ProducerError
from reval.sdk import Context, ProducerOutput, exact_result, interval_result

# Recorded cycles take their input channels from the dataset; declared by column so only these invalidate.
_CYCLE_COLUMNS = "measures[torque,motor_speed,coolant,ambient]"
# Measured node temperatures, used only as the known initial state of recorded segments.
_STATE_COLUMNS = "measures[pm,stator_yoke,stator_tooth,stator_winding]"
_BLOCKS = "motor.cycles:blocks"
_RECORDED = "motor.cycles:recorded"
_NODE = {"pm_peak": "pm", "sw_peak": "stator_winding"}


def _is_duty_cycle(subject: Subject) -> bool:
    return subject.kind is SubjectKind.DUTY_CYCLE and subject.generator in (_BLOCKS, _RECORDED)


def _is_recorded_cycle(subject: Subject) -> bool:
    """Tier A bench measurements exist only for recorded segments of test profiles."""
    return subject.kind is SubjectKind.DUTY_CYCLE and subject.generator == _RECORDED


def _is_design(subject: Subject) -> bool:
    return subject.kind is SubjectKind.DESIGN


def _cycle(subject: Subject, ctx: Context) -> pd.DataFrame:
    """Torque, motor_speed, coolant, ambient (2 Hz) of a duty-cycle subject."""
    if subject.generator == _BLOCKS:
        return cycles.blocks(subject.params)
    if subject.generator == _RECORDED:
        p = subject.params
        df = ctx.load("measures")
        return cycles.recorded(int(p["profile_id"]), float(p["start_s"]), float(p["duration_s"]), df)
    raise ProducerError(f"{subject.id}: unsupported cycle generator {subject.generator!r}")


def _drive_inputs(cycle: pd.DataFrame, drive_map: Any) -> tuple[pd.DataFrame, dict[str, Any], bool]:
    """Model inputs through the drive map, plus its applicability report (docs/05 section 5)."""
    torque = cycle["torque"].to_numpy()
    speed = cycle["motor_speed"].to_numpy()
    inputs = drive_map.to_inputs(torque, speed, cycle["coolant"].to_numpy(), cycle["ambient"].to_numpy())
    report = drive_map.domain_report(torque, speed)
    return inputs, report.to_dict(), bool(report.inside)


def _initial_state(subject: Subject, ctx: Context) -> dict[str, float] | None:
    """Measured node temperatures at the start of a recorded segment; None (cold start) for parametric cycles.

    A recorded segment usually starts mid-profile with a warm machine. Starting it from the coolant
    temperature would under-predict its peak, which is the unsafe direction.
    """
    if subject.generator != _RECORDED:
        return None
    p = subject.params
    df = ctx.load("measures")
    seg = cycles._segment(int(p["profile_id"]), float(p["start_s"]), float(p["duration_s"]), df)
    first = seg.iloc[0]
    return {node: float(first[node]) for node in lptn.NODES}


def _lptn_params(ctx: Context) -> lptn.LPTNParams:
    """Rebuild the LPTN from the three pointer subtrees the producer declared (never the whole file)."""
    flat: dict[str, float] = {}
    for group in ("R", "C", "loss"):
        for name, value in ctx.param(f"lptn#/{group}").items():
            flat[f"/{group}/{name}"] = value
    return lptn._from_flat(flat)


def _tolerances(ctx: Context) -> tuple[Tolerance, ...]:
    """Tolerances from params/tolerances.yaml (scripts/sensitivities.py), sorted for determinism."""
    entries = ctx.load("tolerances")["tolerances"]
    return tuple(sorted((Tolerance.model_validate(e) for e in entries), key=lambda t: t.selector))


def _point_only(quantity: str, unit: str, point: float, report: dict[str, Any]) -> EvidenceResult:
    """Out-of-domain result: no interval, so the verdict is INCONCLUSIVE (fail closed)."""
    return EvidenceResult(
        quantity=quantity,
        unit=unit,
        point=point,
        uncertainty_kind="none",
        in_domain=False,
        domain_report=report,
    )


@reval.producer(
    id="lptn_sim",
    kind="physics_sim",
    quantity=["pm_peak", "sw_peak"],
    fidelity=2,
    cost=5,
    depends_on=[
        "lptn#/R",
        "lptn#/C",
        "lptn#/loss",
        "drive_map",
        "cooling#/flow_scale",
        "tolerances",
        "lptn_report#/model_form_band_K",
        _CYCLE_COLUMNS,
        _STATE_COLUMNS,
    ],
    predictors=["lptn"],
    available_for=_is_duty_cycle,
)
def lptn_sim(subject: Subject, ctx: Context) -> ProducerOutput:
    """Peak node temperature of the independent LPTN, +/- the model-form band of the cycle's length class.

    The band is the observed test-set discrepancy of the LPTN (scripts/calibrate_lptn.py), not a statistical
    guarantee. When the drive map is outside its domain the inputs are extrapolated, so only a point value
    is emitted (inconclusive).
    """
    cycle = _cycle(subject, ctx)
    params = _lptn_params(ctx)
    flow_scale = float(ctx.param("cooling#/flow_scale"))
    inputs, report, inside = _drive_inputs(cycle, ctx.load("drive_map"))
    sim = lptn.simulate(inputs, params, _initial_state(subject, ctx), flow_scale=flow_scale)
    cls = cycles.length_class(len(cycle) * cycles.DT_S)
    results: list[EvidenceResult] = []
    for quantity, node in _NODE.items():
        peak = float(sim[node].max())
        if not inside:
            results.append(_point_only(quantity, "degC", peak, report))
            continue
        band = float(ctx.param(f"lptn_report#/model_form_band_K/{cls}/{node}"))
        results.append(
            interval_result(
                quantity,
                "degC",
                peak,
                peak - band,
                peak + band,
                uncertainty_kind="model_form",
                in_domain=True,
                domain_report=report,
            )
        )
    return ProducerOutput(results=tuple(results), tolerances=_tolerances(ctx))


@reval.producer(
    id="bench_measure",
    kind="measurement",
    quantity=["pm_peak", "sw_peak"],
    fidelity=3,
    cost=100,
    depends_on=["measures[pm,stator_winding]", "cooling#/flow_scale"],
    assumes=["A-sensor-pm", "A-sensor-sw"],
    available_for=_is_recorded_cycle,
)
def bench_measure(subject: Subject, ctx: Context) -> ProducerOutput:
    """Measured peak of the recorded segment +/- the declared sensor uncertainty (Tier A ground truth).

    The flow dependency is declared although the value is not read: the recording was made at the
    nominal bench flow, so a changed ``flow_scale`` makes the measurement stale instead of reusable.
    """
    p = subject.params
    temps = cycles.recorded_temperatures(
        int(p["profile_id"]), float(p["start_s"]), float(p["duration_s"]), ctx.load("measures")
    )
    sensor_k = {
        "pm_peak": ctx.assumption("A-sensor-pm").value,
        "sw_peak": ctx.assumption("A-sensor-sw").value,
    }
    results = []
    for quantity, node in _NODE.items():
        half = sensor_k[quantity]
        if half is None or half <= 0.0:
            raise ProducerError(f"sensor uncertainty for {quantity} must be a positive value (fail closed)")
        peak = float(temps[node].max())
        results.append(
            interval_result(
                quantity, "degC", peak, peak - half, peak + half, uncertainty_kind="sensor", in_domain=True
            )
        )
    return ProducerOutput(results=tuple(results))


@reval.producer(
    id="shaft_check",
    kind="analytic",
    quantity="shaft_d",
    fidelity=3,
    cost=1,
    depends_on=["shaft#/nominal_d_mm", "shaft#/tol_plus_mm"],
    available_for=_is_design,
)
def shaft_check(subject: Subject, ctx: Context) -> ProducerOutput:
    """Largest permitted shaft diameter (nominal plus upper tolerance); independent of every thermal input."""
    d_max = float(ctx.param("shaft#/nominal_d_mm")) + float(ctx.param("shaft#/tol_plus_mm"))
    return ProducerOutput(results=(exact_result("shaft_d", "mm", d_max),))


@reval.producer(
    id="current_limit_check",
    kind="analytic",
    quantity="is_peak",
    fidelity=3,
    cost=1,
    depends_on=["drive_map", _CYCLE_COLUMNS],
    available_for=_is_duty_cycle,
)
def current_limit_check(subject: Subject, ctx: Context) -> ProducerOutput:
    """Peak stator current |i_dq| over the cycle, taken through the drive map.

    Shares the drive map with ``lptn_sim`` (partial overlap for locality tests). Outside the drive map's
    domain the value is an extrapolation, so it is reported as a point only (inconclusive).
    """
    cycle = _cycle(subject, ctx)
    inputs, report, inside = _drive_inputs(cycle, ctx.load("drive_map"))
    peak = float(np.max(add_derived(inputs)["i_s"]))
    if not inside:
        return ProducerOutput(results=(_point_only("is_peak", "A", peak, report),))
    return ProducerOutput(results=(exact_result("is_peak", "A", peak),))
