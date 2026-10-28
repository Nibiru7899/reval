"""B4: random runs up to a cost budget (ReVal's plan cost), with common random numbers."""

from __future__ import annotations

import hashlib

import numpy as np

from bench.baselines.base import PostState, PreState, Run
from bench.oracles.evidence import b0_runs


def priority(scenario_id: str, producer_id: str, subject_id: str) -> float:
    """Per-run random priority; identical for every method and independent of the candidate set."""
    seed = int(hashlib.sha256(f"{scenario_id}|{producer_id}|{subject_id}".encode()).hexdigest()[:8], 16)
    return float(np.random.default_rng(seed).random())


class RandomBudget:
    id = "B4"

    def __init__(self, scenario_id: str, budget: float) -> None:
        self.scenario_id = scenario_id
        self.budget = budget

    def select_runs(self, pre: PreState, post: PostState) -> list[Run]:
        candidates = sorted(
            b0_runs(post.snapshot, post.project),
            key=lambda r: (priority(self.scenario_id, *r), r),
        )
        left = self.budget
        chosen: list[Run] = []
        for pid, sid in candidates:
            cost = post.snapshot.producers[pid].cost
            if cost <= left + 1e-9:
                chosen.append((pid, sid))
                left -= cost
        return sorted(chosen)
