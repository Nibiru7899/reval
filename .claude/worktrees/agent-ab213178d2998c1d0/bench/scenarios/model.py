"""Scenario model, generator config, applier registry (P5-03).

A scenario is fully described by ``(config, seed, index)``: ``params`` holds every sampled value, so an
applier needs nothing but the workspace and the scenario. Samplers are project-agnostic (they pick
*symbolic* targets such as ``R-PM-MAX``); appliers resolve them against the workspace's files.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["A", "B"]
CHANGE_TYPES: tuple[str, ...] = tuple(f"T{i}" for i in range(1, 13))


class Scenario(BaseModel):
    """One benchmark scenario (frozen). ``apply`` names a registered applier."""

    model_config = ConfigDict(frozen=True)

    id: str
    change_type: str
    tier: Tier
    seed: int
    base_snapshot: int = Field(ge=0, description="Cluster id of the base snapshot (bootstrap cluster).")
    params: dict[str, Any]
    apply: str


class SubsetConfig(BaseModel):
    """The pre-registered bench subset of the motor project (phase 5 refinement).

    12 recorded test cycles + 12 parametric cycles (``parametric_out_of_domain`` of them outside the train
    envelope, spread over the three length classes), x 2 thermal targets, + C-SHAFT + ``n_current_limit``
    current-limit claims. One ML model kind keeps retraining cheap.
    """

    model_config = ConfigDict(frozen=True)

    n_recorded: int = 12
    n_parametric: int = 12
    parametric_out_of_domain: int = 3
    n_current_limit: int = 4
    model_kind: Literal["ridge", "hgb", "mlp"] = "hgb"


class GenerateConfig(BaseModel):
    """Generator configuration. Hashed and pre-registered as part of the bench config."""

    model_config = ConfigDict(frozen=True)

    instances_per_type: int = Field(default=10, ge=1)
    n_base_snapshots: int = Field(default=30, ge=1)
    tiers: tuple[Tier, ...] = ("A", "B")
    change_types: tuple[str, ...] = CHANGE_TYPES
    t5_requirements: tuple[str, ...] = ("R-PM-MAX", "R-SW-MAX")
    t6_assumptions: tuple[str, ...] = ("A-coolant-range", "A-flow-sens")
    subset: SubsetConfig = SubsetConfig()


@dataclass
class AppliedChange:
    """What an applier did, for the harness and for tests.

    ``declared`` lists project files edited (the change set ReVal can see); ``retrain`` says which
    models to refit afterwards (applied once per scenario by ``apply_scenario``).
    """

    declared: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)
    retrain_targets: dict[str, dict[str, Any] | None] = field(default_factory=dict)  # target -> hgb hp
    retrain_lptn: bool = False

    def merge(self, other: AppliedChange) -> None:
        self.declared.extend(f for f in other.declared if f not in self.declared)
        self.retrain_targets.update(other.retrain_targets)
        self.retrain_lptn = self.retrain_lptn or other.retrain_lptn
        self.notes.setdefault("components", []).append(other.notes)


Applier = Callable[[Any, Scenario], AppliedChange]  # (Workspace, Scenario)
Sampler = Callable[[np.random.Generator, GenerateConfig], dict[str, Any]]

APPLIERS: dict[str, Applier] = {}
SAMPLERS: dict[tuple[str, Tier], tuple[str, Sampler]] = {}  # (change_type, tier) -> (applier name, sampler)


def register(change_type: str, tier: Tier, name: str, sampler: Sampler) -> Callable[[Applier], Applier]:
    """Register an applier under ``name`` together with the sampler of its parameters."""

    def deco(fn: Applier) -> Applier:
        if name in APPLIERS:
            raise ValueError(f"applier {name!r} registered twice")
        APPLIERS[name] = fn
        SAMPLERS[(change_type, tier)] = (name, sampler)
        return fn

    return deco
