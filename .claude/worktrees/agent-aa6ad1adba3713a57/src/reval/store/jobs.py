"""Background job records (docs/10 §8)."""

from enum import StrEnum
from typing import Any, Literal

from reval.domain.base import Frozen


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(Frozen):
    id: str
    kind: Literal["run_plan", "run"]
    state: JobState
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
