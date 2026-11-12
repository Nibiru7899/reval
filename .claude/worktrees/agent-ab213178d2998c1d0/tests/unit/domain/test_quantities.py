import pytest
from pydantic import ValidationError

from reval.domain import Frozen, Interval
from reval.errors import (
    GitError,
    LockNotFoundError,
    ManifestError,
    MissingExtraError,
    ProducerError,
    RevalError,
    SchemaError,
    StoreError,
    UndeclaredDependencyError,
)


def test_interval_ok() -> None:
    assert Interval(lo=1.0, hi=3.0, unit="K").width == 2.0
    assert Interval(lo=2, hi=2, unit="K").width == 0


def test_interval_lo_gt_hi_raises() -> None:
    with pytest.raises(ValidationError):
        Interval(lo=2, hi=1, unit="K")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_interval_non_finite_raises(bad: float) -> None:
    with pytest.raises(ValidationError):
        Interval(lo=bad, hi=1.0, unit="K")
    with pytest.raises(ValidationError):
        Interval(lo=0.0, hi=bad, unit="K")


def test_widen() -> None:
    iv = Interval(lo=1.0, hi=3.0, unit="degC").widen(0.5)
    assert (iv.lo, iv.hi, iv.unit) == (0.5, 3.5, "degC")
    assert Interval(lo=1.0, hi=3.0, unit="K").widen(0).width == 2.0


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_widen_invalid_raises(bad: float) -> None:
    with pytest.raises(ValueError):
        Interval(lo=1.0, hi=3.0, unit="K").widen(bad)


def test_frozen_and_forbids_extra() -> None:
    iv = Interval(lo=1.0, hi=3.0, unit="K")
    with pytest.raises(ValidationError):
        iv.lo = 0.0  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Interval(lo=1.0, hi=3.0, unit="K", extra=1)  # type: ignore[call-arg]
    assert issubclass(Interval, Frozen)


def test_error_hierarchy() -> None:
    for cls in (
        ManifestError,
        UndeclaredDependencyError,
        ProducerError,
        MissingExtraError,
        GitError,
        StoreError,
        SchemaError,
    ):
        assert issubclass(cls, RevalError)
    assert issubclass(LockNotFoundError, GitError)


def test_missing_extra_message() -> None:
    err = MissingExtraError("motor")
    assert err.extra == "motor"
    assert 'pip install "reval[motor]"' in str(err)
