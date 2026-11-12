import pytest
from pydantic import BaseModel, ValidationError

from reval.domain import (
    Artifact,
    ArtifactKind,
    ArtifactVersion,
    Assumption,
    Claim,
    Comparator,
    Criticality,
    Requirement,
    RowGroupInfo,
    Selector,
    Subject,
    SubjectKind,
)


def test_assumption_bounds_xor_value() -> None:
    Assumption(id="A", statement="s", variable="v", unit="degC", bounds=(10, 40))
    Assumption(id="A", statement="s", variable="v", unit="degC", value=1.0, tol=0.1)
    Assumption(id="A", statement="s", variable="v", unit="degC", value=1.0)
    with pytest.raises(ValidationError):
        Assumption(id="A", statement="s", variable="v", unit="degC", bounds=(1, 2), value=1.0)
    with pytest.raises(ValidationError):
        Assumption(id="A", statement="s", variable="v", unit="degC")
    with pytest.raises(ValidationError):
        Assumption(id="A", statement="s", variable="v", unit="degC", bounds=(5, 1))
    with pytest.raises(ValidationError):
        Assumption(id="A", statement="s", variable="v", unit="degC", bounds=(1, 2), tol=0.1)


def test_requirement_enums() -> None:
    assert Comparator.LE.value == "<=" and Criticality.HIGH.value == "high"
    with pytest.raises(ValidationError):
        Requirement.model_validate(
            {
                "id": "R",
                "text": "t",
                "quantity": "q",
                "op": "<",
                "limit": 1,
                "unit": "mm",
                "criticality": "low",
            }
        )


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Claim(id="C", requirement_id="R", subject_id="S", bogus=1)  # type: ignore[call-arg]


def test_frozen() -> None:
    c = Claim(id="C", requirement_id="R", subject_id="S")
    with pytest.raises(ValidationError):
        c.id = "D"


@pytest.mark.parametrize(
    "obj",
    [
        Selector.parse("a[x,y]"),
        Selector.parse("a#/p"),
        Artifact(
            id="a",
            kind=ArtifactKind.DATASET,
            path="d.csv",
            hasher="dataframe",
            key=("g",),
            derived_from=("b",),
        ),
        RowGroupInfo(n_rows=3, bbox={"x": (0.0, 1.0)}),
        ArtifactVersion(
            artifact_id="a",
            content_hash="h",
            field_hashes={"/a": "1"},
            field_values={"/a": 1.5, "/b": None, "/c": "s", "/d": True},
            row_groups={"g1": RowGroupInfo(n_rows=2, bbox={"x": (0.0, 2.0)})},
        ),
        Assumption(id="A", statement="s", variable="v", unit="degC", bounds=(10, 40)),
        Requirement(
            id="R",
            text="t",
            quantity="temp_peak",
            op=Comparator.LE,
            limit=80.0,
            unit="degC",
            criticality=Criticality.MEDIUM,
        ),
        Subject(id="S", kind=SubjectKind.DUTY_CYCLE, generator="m:f", params={"load": [1, 2]}),
        Claim(id="C", requirement_id="R", subject_id="S", policy_id="p"),
    ],
)
def test_round_trip(obj: BaseModel) -> None:
    assert type(obj).model_validate(obj.model_dump()) == obj
    assert type(obj).model_validate_json(obj.model_dump_json()) == obj
