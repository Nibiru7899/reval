"""Finite-difference LPTN sensitivities as freshness tolerances (docs/04 A3, docs/10 s12).

The sensitivity stored in a ``Tolerance`` is the RAW max |d peak / d field| over grid x cycles. The safety
factor kappa is kept apart in ``Tolerance.safety_factor`` and applied exactly once, at inflation time (D14).
The estimate is empirical, not a proof.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from motor import lptn
from reval.domain.evidence import Tolerance

FLOW_FIELD = "cooling#/flow_scale"
# Both claimed nodes (pm_peak, sw_peak) are scanned; the larger slope wins (conservative).
_NODES = ("pm", "stator_winding")

# simulator(params, flow_scale, cycle) -> {node: peak degC}. Injectable so tests can use a linear toy.
Simulator = Callable[[lptn.LPTNParams, float, Mapping[str, Any]], Mapping[str, float]]

_UNITS = {"R": "K/W", "C": "J/K", "loss": "dimensionless"}


def params_hash(params: lptn.LPTNParams) -> str:
    """Short content hash of the LPTN parameters, recorded in ``Tolerance.source``."""
    flat = lptn._to_flat(params)
    return hashlib.sha256(json.dumps(flat, sort_keys=True).encode()).hexdigest()[:12]


def simulate_peaks(
    params: lptn.LPTNParams, flow_scale: float, cycle: Mapping[str, Any]
) -> Mapping[str, float]:
    """Default simulator: node peaks of one cycle (``cycle`` has ``inputs`` and optional ``theta0``)."""
    sim = lptn.simulate(cycle["inputs"], params, cycle.get("theta0"), flow_scale=flow_scale)
    return {n: float(sim[n].max()) for n in _NODES}


def _apply(params: lptn.LPTNParams, field: str, value: float) -> tuple[lptn.LPTNParams, float, str]:
    """(params, flow_scale, input_unit) with ``field`` set to ``value``; other inputs nominal."""
    if field == FLOW_FIELD:
        return params, value, "dimensionless"
    artifact, _, pointer = field.partition("#")
    parts = pointer.split("/")
    if artifact != "lptn" or len(parts) != 3 or parts[1] not in _UNITS:
        raise ValueError(f"unsupported tolerance field {field!r}")
    flat = lptn._to_flat(params)
    if pointer not in flat:
        raise ValueError(f"unknown LPTN leaf {field!r}")
    flat[pointer] = value
    return lptn._from_flat(flat), 1.0, _UNITS[parts[1]]


def estimate_tolerances(
    params: lptn.LPTNParams,
    field: str,
    grid: Sequence[float],
    cycles: Sequence[Mapping[str, Any]],
    *,
    assumption_id: str,
    kappa: float = 1.5,
    simulator: Simulator = simulate_peaks,
) -> list[Tolerance]:
    """Tolerance for ``field`` from central finite differences over ``grid`` x ``cycles``.

    ``sensitivity`` is the raw max |delta peak / delta field| in K per input unit (one-sided at the two
    grid ends); ``valid_range`` is the grid span. ``kappa`` is only stored.
    """
    pts = sorted(float(g) for g in grid)
    if len(pts) < 5 or len(set(pts)) != len(pts):
        raise ValueError("grid needs >= 5 distinct points spanning the valid range")
    if not cycles:
        raise ValueError("at least one cycle is required")
    slope = 0.0
    unit = ""
    for cycle in cycles:
        peaks: dict[str, list[float]] = {n: [] for n in _NODES}
        for x in pts:
            p, flow, unit = _apply(params, field, x)
            out = simulator(p, flow, cycle)
            for n in _NODES:
                peaks[n].append(float(out[n]))
        for n in _NODES:
            slope = max(slope, float(np.max(np.abs(np.gradient(np.asarray(peaks[n]), np.asarray(pts))))))
    return [
        Tolerance(
            selector=field,
            sensitivity=slope,
            input_unit=unit,
            output_unit="K",
            valid_range=(pts[0], pts[-1]),
            safety_factor=kappa,
            source=f"fd on lptn@{params_hash(params)}, grid={len(pts)}, cycles={len(cycles)}",
            assumption_id=assumption_id,
        )
    ]
