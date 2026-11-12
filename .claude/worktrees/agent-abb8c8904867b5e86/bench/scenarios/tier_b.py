"""Tier B appliers (T6-B, T7, T8, T9, T12) (P5-06).

Tier B scenarios run on the world-trained base snapshot (``bench.world.base``). A *declared* change edits
project files and also changes the world; T9 changes only the world, so its change set is empty and only
the undeclared measurement table ``bench_measurements.json`` is regenerated (the "physical world").
The measurement noise is common-random-number seeded by the scenario id, identical for S and S'
(the base snapshot must be built with ``seed=scenario.id``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from bench.scenarios.model import (
    APPLIERS,
    SAMPLERS,
    AppliedChange,
    GenerateConfig,
    Scenario,
    Tier,
    register,
)
from bench.scenarios.tier_a import (
    MEASURES,
    SUBJECTS,
    _root,
    _sample_t6,
    edit_assumption,
    load_yaml,
)
from bench.world import PhysicalParams, World
from bench.world.base import MEASUREMENTS_FILE, bench_measurements, world_trajectories

COOLING = "params/cooling.yaml"
WORLD_JSON = Path(__file__).resolve().parents[1] / "cache" / "world" / "world.json"
_WORLD: World | None = None
APPLICABLE: dict[str, tuple[str, ...]] = {
    "A": ("T1", "T2", "T3", "T4", "T5", "T6", "T10", "T11"),
    "B": ("T5", "T6", "T7", "T8", "T9", "T10", "T11"),
}
_EXCLUSIVE = (("T1", "T2"), ("T7", "T8"))  # at most one of each group in a compound
_COMPOUND = ("t12_compound_a", "t12_compound_b")


def use_world(world: World | None) -> None:
    """Inject the world used to regenerate measurement tables (tests, or a world built by the runner)."""
    global _WORLD
    _WORLD = world


def bench_world() -> World:
    """The calibrated world: the injected one, else the cached ``bench/cache/world/world.json``."""
    if _WORLD is not None:
        return _WORLD
    if not WORLD_JSON.exists():
        raise FileNotFoundError(f"calibrated world not found at {WORLD_JSON}; run get_world first")
    from bench.world.calibrate import load_world  # needs motor on sys.path; imported lazily

    return load_world(WORLD_JSON)


def components(sc: Scenario) -> list[Scenario]:
    """The scenario itself, or its sub-scenarios for a compound (ids ``<id>#k``)."""
    if sc.apply not in _COMPOUND:
        return [sc]
    return [
        Scenario(
            id=f"{sc.id}#{k}",
            change_type=c["change_type"],
            tier=sc.tier,
            seed=sc.seed,
            base_snapshot=sc.base_snapshot,
            params={**c["params"], "defer_measurements": True},
            apply=c["apply"],
        )
        for k, c in enumerate(sc.params["components"])
    ]


def world_physical_params(sc: Scenario, base: PhysicalParams | None = None) -> PhysicalParams:
    """Physical parameters of the plant in S' (declared flow changes and T9 degradation composed)."""
    base = base or PhysicalParams()
    flow, r_ic = base.coolant_flow_scale, base.R_ic_scale
    for c in components(sc):
        if c.apply in ("t7_flow_small", "t8_flow_large"):
            flow *= 1.0 + float(c.params["flow_change"])
        elif c.apply == "t9_degradation":
            r_ic *= float(c.params["r_ic_scale"])
    return PhysicalParams(R_ic_scale=r_ic, coolant_flow_scale=flow, sensor_offset=base.sensor_offset)


def regenerate_measurements(
    ws: Any, sc: Scenario, base: PhysicalParams | None = None, world: World | None = None
) -> dict[str, dict[str, float]]:
    """Rewrite ``bench_measurements.json`` for the plant of S' (undeclared; CRN seed = scenario id)."""
    root = _root(ws)
    world = world or bench_world()
    phys = world_physical_params(sc, base)
    df = pd.read_parquet(root / MEASURES)
    traj = world_trajectories(world, df, phys)
    table = bench_measurements(world, traj, load_yaml(root / SUBJECTS), phys, sc.id)
    (root / MEASUREMENTS_FILE).write_text(json.dumps(table, indent=2, sort_keys=True), encoding="utf-8")
    return table


def _finish(ws: Any, sc: Scenario, change: AppliedChange) -> AppliedChange:
    if not sc.params.get("defer_measurements"):
        regenerate_measurements(ws, sc)
    return change


# --- T6-B -----------------------------------------------------------------------------------------------
@register("T6", "B", "t6b_assumption", _sample_t6)
def apply_t6b(ws: Any, sc: Scenario) -> AppliedChange:
    """Assumption range change in Tier B (the plant is unchanged; the table is rewritten identically)."""
    return _finish(ws, sc, edit_assumption(_root(ws), sc.params))


# --- T7 / T8 / T9 ---------------------------------------------------------------------------------------
def _sample_t7(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    return {"flow_change": -round(float(rng.uniform(0.02, 0.08)), 3)}


def _sample_t8(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    return {"flow_change": -round(float(rng.uniform(0.15, 0.35)), 3)}


def _sample_t9(rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    return {"r_ic_scale": round(float(rng.uniform(1.1, 1.4)), 3)}


_FLOW = re.compile(r"(?m)^(flow_scale:\s*)([0-9.]+)")


def edit_flow_scale(root: Path, flow_change: float) -> AppliedChange:
    """Multiply ``cooling#/flow_scale`` by ``1 + flow_change`` (the declared design change)."""
    f = root / COOLING
    text = f.read_bytes().decode("utf-8")
    m = _FLOW.search(text)
    if m is None:
        raise ValueError(f"flow_scale not found in {COOLING}")
    old = float(m.group(2))
    new = round(old * (1.0 + flow_change), 4)
    f.write_bytes(_FLOW.sub(lambda mm: f"{mm.group(1)}{new}", text, count=1).encode("utf-8"))
    return AppliedChange([COOLING], {"flow_scale_old": old, "flow_scale_new": new})


@register("T7", "B", "t7_flow_small", _sample_t7)
def apply_t7(ws: Any, sc: Scenario) -> AppliedChange:
    """Small declared coolant-flow reduction (-2..-8 %), in the params file and in the world."""
    return _finish(ws, sc, edit_flow_scale(_root(ws), float(sc.params["flow_change"])))


@register("T8", "B", "t8_flow_large", _sample_t8)
def apply_t8(ws: Any, sc: Scenario) -> AppliedChange:
    """Large declared coolant-flow reduction (-15..-35 %), in the params file and in the world."""
    return _finish(ws, sc, edit_flow_scale(_root(ws), float(sc.params["flow_change"])))


@register("T9", "B", "t9_degradation", _sample_t9)
def apply_t9(ws: Any, sc: Scenario) -> AppliedChange:
    """Undeclared degradation: world R_ic grows, **no project file changes**, only the measurement table."""
    return _finish(ws, sc, AppliedChange([], {"r_ic_scale": sc.params["r_ic_scale"]}))


# --- T12: compound --------------------------------------------------------------------------------------
def component_sampler(change_type: str, tier: Tier) -> tuple[str, Any]:
    """(applier name, sampler) of a change type; T5/T10/T11 are shared with Tier B (file edits only)."""
    return SAMPLERS.get((change_type, tier)) or SAMPLERS[(change_type, "A")]


def _sample_compound(tier: Tier, rng: np.random.Generator, cfg: GenerateConfig) -> dict[str, Any]:
    pool = [t for t in APPLICABLE[tier] if t in cfg.change_types or t in ("T5", "T10", "T11")]
    k = int(rng.integers(2, 4))
    chosen: list[str] = []
    for ct in (str(x) for x in rng.permutation(pool)):
        if any(ct in g and any(o in chosen for o in g) for g in _EXCLUSIVE):
            continue
        chosen.append(ct)
        if len(chosen) == k:
            break
    comps = []
    for ct in sorted(chosen, key=lambda t: int(t[1:])):
        name, sampler = component_sampler(ct, tier)
        comps.append({"change_type": ct, "apply": name, "params": sampler(rng, cfg)})
    return {"components": comps}


def apply_compound(ws: Any, sc: Scenario) -> AppliedChange:
    """Apply 2-3 component changes in order; refits are merged and the measurement table is rewritten once."""
    out = AppliedChange()
    for sub in components(sc):
        out.merge(APPLIERS[sub.apply](ws, sub))
    if sc.tier == "B":
        regenerate_measurements(ws, sc)
    return out


register("T12", "A", "t12_compound_a", lambda rng, cfg: _sample_compound("A", rng, cfg))(apply_compound)
register("T12", "B", "t12_compound_b", lambda rng, cfg: _sample_compound("B", rng, cfg))(apply_compound)
