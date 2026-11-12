"""Response models that have no domain counterpart. Domain and report models are never redefined here."""

from typing import Literal

from reval.domain import Assessment, ChangeSet, FreshnessClass, Reason, Status
from reval.domain.base import Frozen


class Health(Frozen):
    status: str
    version: str


class ProjectInfo(Frozen):
    id: str
    name: str
    claims: int


class SnapshotSummary(Frozen):
    id: str
    git_rev: str | None
    claims: int


class FreshnessEntry(Frozen):
    cls: FreshnessClass
    inflation: float
    reasons: tuple[Reason, ...]


class DiffResponse(Frozen):
    from_snapshot: str
    to_snapshot: str
    changes: ChangeSet
    freshness: dict[str, FreshnessEntry]
    before: dict[str, Assessment]
    after: dict[str, Assessment]
    affected_claims: tuple[str, ...]


class Justification(Frozen):
    claim_id: str
    snapshot_id: str
    text: str


class GraphNode(Frozen):
    id: str
    type: str
    label: str
    status: Status | None = None  # claim nodes only


class GraphEdge(Frozen):
    source: str
    target: str
    type: str


class GraphResponse(Frozen):
    snapshot_id: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


class PlanRequest(Frozen):
    snapshot: str | None = None
    budget: float | None = None
    planner: Literal["ilp", "greedy", "all"] = "ilp"


class SnapshotRef(Frozen):
    snapshot: str | None = None


class JobRef(Frozen):
    job_id: str
