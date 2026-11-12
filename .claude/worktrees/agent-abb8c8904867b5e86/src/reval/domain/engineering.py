"""Engineering entities: assumptions, requirements, subjects, claims (docs/10-interfaces.md §2)."""

import math
from enum import StrEnum
from typing import Any, Self

from pydantic import model_validator

from reval.domain.base import Frozen


class Assumption(Frozen):
    """Either a bounded variable (``bounds``) or a nominal ``value`` with optional ``tol``."""

    id: str
    statement: str
    variable: str
    unit: str
    bounds: tuple[float, float] | None = None
    value: float | None = None
    tol: float | None = None

    @model_validator(mode="after")
    def _exactly_one_form(self) -> Self:
        has_bounds = self.bounds is not None
        has_value = self.value is not None
        if has_bounds == has_value:
            raise ValueError("assumption needs exactly one of `bounds` or `value[, tol]`")
        if has_bounds:
            assert self.bounds is not None
            if self.tol is not None:
                raise ValueError("`tol` goes with `value`, not `bounds`")
            lo, hi = self.bounds
            if not (math.isfinite(lo) and math.isfinite(hi) and lo <= hi):
                raise ValueError("bounds must be finite with lo <= hi")
        elif self.tol is not None and (not math.isfinite(self.tol) or self.tol < 0):
            raise ValueError("tol must be finite and >= 0")
        return self


class Criticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Comparator(StrEnum):
    LE = "<="
    GE = ">="


class Requirement(Frozen):
    """``limit`` is absolute and in the canonical unit of ``quantity``."""

    id: str
    text: str
    quantity: str
    op: Comparator
    limit: float
    unit: str
    criticality: Criticality


class SubjectKind(StrEnum):
    DUTY_CYCLE = "duty_cycle"
    DESIGN = "design"
    OPERATING_POINT = "operating_point"


class Subject(Frozen):
    id: str
    kind: SubjectKind
    generator: str | None = None
    params: dict[str, Any] = {}  # noqa: RUF012  (pydantic copies defaults)


class Claim(Frozen):
    id: str
    requirement_id: str
    subject_id: str
    policy_id: str | None = None
