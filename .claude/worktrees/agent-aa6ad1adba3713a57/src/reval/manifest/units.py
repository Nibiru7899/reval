"""Unit handling with pint (the only module in ReVal that imports pint)."""

from functools import lru_cache
from typing import Any

import pint

from reval.errors import ManifestError


@lru_cache(maxsize=1)
def _registry() -> pint.UnitRegistry:
    return pint.UnitRegistry()


def validate_unit(unit: str, *, location: str | None = None) -> None:
    """Raise ManifestError if ``unit`` is not a parseable pint unit."""
    try:
        _registry().Unit(unit)
    except Exception as exc:  # pint raises several error types for bad names
        raise ManifestError(f"unknown unit {unit!r}", location=location) from exc


def convert(value: float, unit: str, canonical: str, *, location: str | None = None) -> float:
    """Convert an absolute value to ``canonical``; offset units (degF -> degC) are handled by pint.

    The result is rounded to 12 significant digits so that e.g. 176 degF gives exactly 80 degC
    rather than 80.00000000000001.
    """
    if unit == canonical:
        return float(value)
    ureg = _registry()
    try:
        q: Any = ureg.Quantity(value, unit).to(canonical)
    except pint.DimensionalityError as exc:
        raise ManifestError(f"unit {unit!r} is not convertible to {canonical!r}", location=location) from exc
    except Exception as exc:
        raise ManifestError(f"cannot convert {unit!r} to {canonical!r}: {exc}", location=location) from exc
    return float(f"{float(q.magnitude):.12g}")
