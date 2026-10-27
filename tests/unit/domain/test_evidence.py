from typing import Any

import pytest
from pydantic import ValidationError

from reval.core.canonical import content_id
from reval.domain import (
    Dependency,
    Evidence,
    EvidenceResult,
    Interval,
    Producer,
    ProducerKind,
    Provenance,
    Scope,
    Tolerance,
    Waiver,
)


def _fields(**over: Any) -> dict[str, Any]:
    f: dict[str, Any] = {
        "producer_id": "m:p",
        "producer_kind": ProducerKind.ML_PREDICTION,
        "fidelity": 1,
        "subject_id": "S1",
        "result": EvidenceResult(
            quantity="temp_peak",
            unit="degC",
            point=70.0,
            interval=Interval(lo=68.0, hi=72.0, unit="degC"),
            uncertainty_kind="conformal",
            in_domain=True,
        ),
        "deps": (Dependency(selector="surrogate", version_hash="h1"),),
        "scope": Scope(box={"x": (0.0, 1.0)}, assumption_ids=("A",)),
        "provenance": Provenance(producer_code_hash="c", snapshot_id="s", env={"numpy": "2"}, seed=1),
        "cost": 1.0,
    }
    f.update(over)
    return f


def _tol(**over: Any) -> Tolerance:
    f: dict[str, Any] = {
        "selector": "params#/load/scale",
        "sensitivity": 2.0,
        "input_unit": "1",
        "output_unit": "K",
        "valid_range": (0.5, 1.5),
        "source": "finite difference",
        "assumption_id": "A-sim-sens",
    }
    f.update(over)
    return Tolerance(**f)


def test_create_id_and_roundtrip() -> None:
    e = Evidence.create(**_fields(tolerances=(_tol(),)))
    assert e.id == content_id(e)
    assert Evidence.model_validate(e.model_dump()) == e
    assert Evidence.model_validate_json(e.model_dump_json()) == e


def test_wrong_id_rejected() -> None:
    with pytest.raises(ValidationError):
        Evidence(id="0" * 64, **_fields())


@pytest.mark.parametrize(
    "over",
    [
        {"producer_id": "m:q"},
        {"fidelity": 2},
        {"subject_id": "S2"},
        {"cost": 2.0},
        {"deps": (Dependency(selector="surrogate", version_hash="h2"),)},
        {"scope": Scope()},
        {"provenance": Provenance(producer_code_hash="c2", snapshot_id="s")},
        {"derived_from_evidence": "x"},
        {"tolerances": (_tol(),)},
        {"result": EvidenceResult(quantity="temp_peak", unit="degC", point=71.0)},
    ],
)
def test_changing_any_field_changes_id(over: dict[str, Any]) -> None:
    assert Evidence.create(**_fields()).id != Evidence.create(**_fields(**over)).id


def test_waiver_required_iff_waiver_kind() -> None:
    w = Waiver(author="a", justification="because", claim_id="C", requirement_hash="h")
    with pytest.raises(ValidationError):
        Evidence.create(**_fields(waiver=w))
    with pytest.raises(ValidationError):
        Evidence.create(**_fields(producer_kind=ProducerKind.WAIVER, fidelity=0))
    e = Evidence.create(**_fields(producer_kind=ProducerKind.WAIVER, fidelity=0, waiver=w))
    assert e.waiver == w
    assert Evidence.model_validate(e.model_dump()) == e


def test_waiver_validation() -> None:
    with pytest.raises(ValidationError):
        Waiver(author="a", justification=" ", claim_id="C", requirement_hash="h")
    with pytest.raises(ValidationError):
        Waiver(author="a", justification="x", claim_id="", requirement_hash="h")
    with pytest.raises(ValidationError):
        Waiver(author="a", justification="x", claim_id="C", requirement_hash="")


def _producer(**over: Any) -> Producer:
    f: dict[str, Any] = {
        "id": "m:p",
        "kind": ProducerKind.ML_PREDICTION,
        "quantities": ("temp_peak",),
        "fidelity": 1,
        "cost": 1.0,
        "code_hash": "c",
        "depends_on": ("params#/load/scale", "surrogate"),
        "predictors": ("surrogate",),
    }
    f.update(over)
    return Producer(**f)


def test_producer_predictor_must_be_dependency() -> None:
    p = _producer()
    assert Producer.model_validate(p.model_dump()) == p
    with pytest.raises(ValidationError):
        _producer(predictors=("other",))
    _producer(depends_on=("surrogate[a,b]",))  # column selector on the predictor still counts


def test_producer_cost() -> None:
    with pytest.raises(ValidationError):
        _producer(cost=0.0)
    _producer(kind=ProducerKind.WAIVER, cost=0.0, fidelity=0, predictors=())


@pytest.mark.parametrize(
    "over",
    [
        {"sensitivity": -1.0},
        {"safety_factor": 0.99},
        {"source": " "},
        {"assumption_id": ""},
        {"selector": "params"},
        {"selector": "data[temp]"},
        {"valid_range": (2.0, 1.0)},
    ],
)
def test_tolerance_invalid(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _tol(**over)


def test_tolerance_default_kappa() -> None:
    assert _tol().safety_factor == 1.5
    with pytest.raises(ValidationError):
        Tolerance.model_validate({k: v for k, v in _tol().model_dump().items() if k != "assumption_id"})
