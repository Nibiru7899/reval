"""Deterministic scenario generator (P5-03): ``generate(config, seed) -> list[Scenario]``.

Every scenario's parameters are drawn from a generator keyed by (seed, tier, change type, index), so the
same ``(config, seed)`` always gives the identical list. Scenarios are dealt round-robin to
``n_base_snapshots`` base-snapshot clusters per tier (docs/06 section 2: at least 30).
"""

from __future__ import annotations

import numpy as np

from bench.scenarios import tier_a, tier_b  # noqa: F401  (import registers the appliers)
from bench.scenarios.model import SAMPLERS, GenerateConfig, Scenario, Tier

TIER_TYPES: dict[Tier, tuple[str, ...]] = {
    "A": ("T1", "T2", "T3", "T4", "T5", "T6", "T10", "T11", "T12"),
    "B": ("T6", "T7", "T8", "T9", "T12"),
}


def generate(config: GenerateConfig, seed: int) -> list[Scenario]:
    """All scenarios of ``config``: ``instances_per_type`` per (tier, change type), tiers kept separate."""
    out: list[Scenario] = []
    for tier in config.tiers:
        counter = 0
        for change_type in TIER_TYPES[tier]:
            if change_type not in config.change_types:
                continue
            apply_name, sampler = SAMPLERS[(change_type, tier)]
            for i in range(config.instances_per_type):
                s = tier_a.crn_seed(seed, tier, change_type, i)
                params = sampler(np.random.default_rng(s), config)
                out.append(
                    Scenario(
                        id=f"{tier}-{change_type}-{i:03d}-s{seed}",
                        change_type=change_type,
                        tier=tier,
                        seed=s,
                        base_snapshot=counter % config.n_base_snapshots,
                        params=params,
                        apply=apply_name,
                    )
                )
                counter += 1
    return out
