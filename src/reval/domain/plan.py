"""Revalidation planning models (docs/10-interfaces.md §2, docs/04 A7)."""

from typing import Literal

from reval.domain.base import Frozen
from reval.domain.policies import EvidenceRequirement


class Obligation(Frozen):
    claim_id: str
    clause_index: int
    conjunct_index: int
    requirement: EvidenceRequirement

    @property
    def key(self) -> str:
        """``<claim_id>/<clause_index>/<conjunct_index>``."""
        return f"{self.claim_id}/{self.clause_index}/{self.conjunct_index}"


class CandidateRun(Frozen):
    id: str
    producer_id: str
    subject_id: str
    cost: float
    satisfies: tuple[str, ...]
    predictors: tuple[str, ...] = ()
    existing_evidence_id: str | None = None


class PlanningProblem(Frozen):
    snapshot_id: str
    claim_weights: dict[str, int]
    clauses: dict[str, tuple[tuple[str, ...], ...]]
    obligations: dict[str, Obligation]
    candidates: tuple[CandidateRun, ...]
    incompatible: tuple[tuple[str, str, str, str], ...] = ()


class PlannedRun(Frozen):
    candidate_id: str
    producer_id: str
    subject_id: str
    cost: float
    discharges: tuple[str, ...]


class RevalidationPlan(Frozen):
    id: str
    snapshot_id: str
    planner: Literal["ilp", "greedy", "all"]
    objective: Literal["min_cost", "max_restored"]
    budget: float | None = None
    runs: tuple[PlannedRun, ...]
    total_cost: float
    chosen_clauses: dict[str, int]
    unrestorable: tuple[str, ...]
    deferred: tuple[str, ...] = ()
    solver_status: str
    reproducible: bool = True
