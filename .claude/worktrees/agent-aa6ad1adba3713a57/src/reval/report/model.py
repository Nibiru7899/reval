"""Canonical report model (docs/09 "Report format"); the JSON form is the source for every rendering."""

from typing import Any

from reval.core.canonical import content_id
from reval.domain import Frozen, Interval

# Mandatory on every report and rendering (AGENTS rule 9); never reworded per renderer.
DISCLAIMER = (
    "ReVal reports the state of recorded evidence against declared requirements. It does not certify safety."
)

HASH_EXCLUDE = frozenset({"report_hash", "report_id", "created_at"})


class ReportEvidence(Frozen):
    id: str
    producer: str
    producer_kind: str
    subject_id: str
    verdict: str
    recorded_verdict: str | None = None
    freshness: str
    point: float | None = None
    interval: Interval | None = None
    used_in_clause: bool = False
    derived_from_evidence: str | None = None
    provenance: dict[str, Any] = {}  # noqa: RUF012  (pydantic copies defaults)


class ReportReason(Frozen):
    code: str
    message: str
    evidence_ids: tuple[str, ...] = ()


class ReportClaim(Frozen):
    id: str
    requirement_id: str
    requirement: str
    quantity: str
    op: str
    limit: float
    unit: str
    criticality: str
    subject: str
    status: str
    satisfied_clause: int | None = None
    reasons: tuple[ReportReason, ...] = ()
    evidence: tuple[ReportEvidence, ...] = ()
    input_hash: str


class ReportChange(Frozen):
    kind: str
    target: str
    old: str | None = None
    new: str | None = None
    delta: float | None = None
    detail: str | None = None


class ReportPlanRun(Frozen):
    producer_id: str
    subject_id: str
    cost: float
    discharges: tuple[str, ...] = ()


class ReportPlan(Frozen):
    plan_id: str
    planner: str
    objective: str
    budget: float | None = None
    solver_status: str
    runs: tuple[ReportPlanRun, ...] = ()
    total_cost: float
    unrestorable: tuple[str, ...] = ()
    deferred: tuple[str, ...] = ()


class Report(Frozen):
    report_id: str
    created_at: str
    reval_version: str
    project: str
    snapshot_id: str
    git_rev: str | None = None
    disclaimer: str
    summary: dict[str, int]
    claims: tuple[ReportClaim, ...]
    changes: tuple[ReportChange, ...] = ()
    plan: ReportPlan | None = None
    hashes: dict[str, str]  # claim id -> assessment input_hash
    report_hash: str


def compute_report_hash(body: dict[str, Any]) -> str:
    """``content_id`` over everything except the time-dependent and self-referential fields (D19)."""
    return content_id(body, exclude=HASH_EXCLUDE)
