"""Claim assessments (docs/10-interfaces.md §2). Append-only records."""

from typing import Any

from reval.domain.base import Frozen
from reval.domain.quantities import Interval
from reval.domain.status import FreshnessClass, ReasonCode, Status, Verdict


class Reason(Frozen):
    code: ReasonCode
    message: str
    evidence_ids: tuple[str, ...] = ()
    detail: dict[str, Any] = {}  # noqa: RUF012  (pydantic copies defaults)


class EvidenceUse(Frozen):
    evidence_id: str
    verdict: Verdict
    freshness: FreshnessClass
    interval_used: Interval | None = None
    used_in_clause: bool = False
    derived_from_evidence: str | None = None
    recorded_verdict: Verdict | None = None


class Assessment(Frozen):
    claim_id: str
    snapshot_id: str
    status: Status
    reasons: tuple[Reason, ...]
    evidence: tuple[EvidenceUse, ...]
    satisfied_clause: int | None = None
    input_hash: str
