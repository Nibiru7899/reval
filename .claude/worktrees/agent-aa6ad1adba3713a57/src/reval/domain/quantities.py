"""Quantities: intervals in a quantity's canonical unit (docs/10-interfaces.md §2)."""

import math
from typing import Self

from pydantic import model_validator

from reval.domain.base import Frozen


class Interval(Frozen):
    """Closed interval [lo, hi] in `unit`, the quantity's canonical unit."""

    lo: float
    hi: float
    unit: str

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if not (math.isfinite(self.lo) and math.isfinite(self.hi)):
            raise ValueError("interval bounds must be finite")
        if self.lo > self.hi:
            raise ValueError(f"interval requires lo <= hi, got lo={self.lo}, hi={self.hi}")
        return self

    def widen(self, delta: float) -> Self:
        """Return [lo-delta, hi+delta]; `delta` (difference unit) must be finite and >= 0."""
        if not math.isfinite(delta) or delta < 0:
            raise ValueError(f"widen requires a finite delta >= 0, got {delta}")
        return type(self)(lo=self.lo - delta, hi=self.hi + delta, unit=self.unit)

    @property
    def width(self) -> float:
        """hi - lo."""
        return self.hi - self.lo
