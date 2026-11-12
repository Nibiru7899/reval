import numpy as np
import pytest

from reval.core.canonical import canonical_json
from reval.uq.domain import ApplicabilityDomain, DomainReport, combine_reports

NAMES = ["a", "b"]


def _reports() -> tuple[DomainReport, DomainReport]:
    rng = np.random.default_rng(0)
    ad = ApplicabilityDomain(NAMES).fit(rng.normal(size=(2000, 2)), rng.normal(size=(500, 2)))
    return ad.check(np.zeros((3, 2))), ad.check(np.full((3, 2), 20.0))


def test_all_inside() -> None:
    ok, _ = _reports()
    out = combine_reports({"drive_map": ok, "model": ok})
    assert out["inside"] is True and out["first_failing_part"] is None
    assert set(out["parts"]) == {"drive_map", "model"}


def test_one_failing_part_is_named_and_serializable() -> None:
    ok, bad = _reports()
    out = combine_reports({"model": bad, "drive_map": ok})
    assert out["inside"] is False
    assert out["first_failing_part"] == "model"
    assert canonical_json(out)
    both = combine_reports({"z": bad, "m": bad, "a": ok})
    assert both["first_failing_part"] == "m"


def test_empty_raises() -> None:
    with pytest.raises(ValueError):
        combine_reports({})
