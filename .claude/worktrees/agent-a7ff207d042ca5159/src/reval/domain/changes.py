"""Change records between two snapshots (docs/10-interfaces.md §2)."""

from enum import StrEnum

from reval.domain.base import Frozen


class ChangeKind(StrEnum):
    FIELD_CHANGED = "field_changed"
    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    ROWS_ADDED = "rows_added"
    ROWS_MODIFIED = "rows_modified"
    ROWS_REMOVED = "rows_removed"
    ARTIFACT_ADDED = "artifact_added"
    ARTIFACT_REMOVED = "artifact_removed"
    ARTIFACT_CHANGED = "artifact_changed"
    REQUIREMENT_CHANGED = "requirement_changed"
    ASSUMPTION_CHANGED = "assumption_changed"
    POLICY_CHANGED = "policy_changed"
    SUBJECT_CHANGED = "subject_changed"
    CLAIM_CHANGED = "claim_changed"
    PRODUCER_CODE_CHANGED = "producer_code_changed"
    UNKNOWN = "unknown"


class Change(Frozen):
    kind: ChangeKind
    target: str
    old: float | int | str | bool | None = None
    new: float | int | str | bool | None = None
    delta: float | None = None
    groups: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    rows_bbox: dict[str, tuple[float, float]] | None = None
    detail: str | None = None


class ChangeSet(Frozen):
    from_snapshot: str
    to_snapshot: str
    changes: tuple[Change, ...]
