"""Per-claim result records: one row per (scenario, method, claim). All metrics derive from these."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from reval.domain.status import Status

#: Statuses that count as "decided" after the plan ran (WAIVED is excluded from the analysis altogether).
DECIDED: frozenset[str] = frozenset({Status.SUPPORTED.value, Status.VIOLATED.value})


@dataclass(frozen=True)
class ClaimRecord:
    """One claim of one scenario under one method.

    Scenario-level quantities (``cost``, ``b0_cost``, ``false_alarm_cost``, ``n_bench_runs``, ``ilp_cost``,
    ``greedy_cost``) are repeated on every claim row of the (scenario, method) group and must agree within it;
    the metrics count them once per group. ``truth_violated`` is ``None`` where the oracle has no truth
    (Tier A non-test subjects). ``reproducible`` is ``None`` when re-execution was not performed.
    """

    scenario_id: str
    change_type: str  # "T1" ... "T12"
    tier: str  # "A" | "B"; never pooled
    base_snapshot: str  # bootstrap cluster
    method: str  # "reval" | "B0" ... "B4" | ablation id
    claim_id: str
    status_before: str
    status_after: str
    accepted: bool  # method accepts the claim in S' (SUPPORTED)
    b0_accepted: bool  # B0 (rerun-all) accepts it in S'
    truly_affected: bool  # evidence oracle
    predicted_affected: bool  # method says status changed or some evidence is not exact-fresh
    truth_violated: bool | None
    cost: float  # plan cost of this method in this scenario
    b0_cost: float
    false_alarm_cost: float = 0.0  # cost of runs whose value moved < epsilon
    n_bench_runs: int = 0
    reproducible: bool | None = None
    ilp_cost: float | None = None
    greedy_cost: float | None = None
    cost_profile: str = "default"  # P5-14: bench-cost profile of the run ("bench20", ...)


_COLUMNS = [f.name for f in dataclasses.fields(ClaimRecord)]


def to_frame(records: Iterable[ClaimRecord]) -> pd.DataFrame:
    """Tidy DataFrame (nullable columns keep ``None`` as missing, never as False/0)."""
    df = pd.DataFrame([dataclasses.asdict(r) for r in records], columns=_COLUMNS)
    for c in ("truth_violated", "reproducible"):
        df[c] = df[c].astype("boolean")
    for c in ("ilp_cost", "greedy_cost"):
        df[c] = df[c].astype("float64")
    return df
