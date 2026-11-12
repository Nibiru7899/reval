from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from reval.core.canonical import content_id
from reval.domain import (
    DEFAULT_POLICIES,
    Artifact,
    ArtifactKind,
    ArtifactVersion,
    Assessment,
    Assumption,
    CandidateRun,
    Change,
    ChangeKind,
    ChangeSet,
    Claim,
    Comparator,
    Criticality,
    EvidenceRequirement,
    EvidenceUse,
    FreshnessClass,
    Interval,
    Obligation,
    PlannedRun,
    PlanningProblem,
    Reason,
    ReasonCode,
    Requirement,
    RevalidationPlan,
    Snapshot,
    Status,
    Subject,
    SubjectKind,
    Verdict,
)


def _fields(reverse: bool = False) -> dict[str, Any]:
    arts = {
        "params": Artifact(id="params", kind=ArtifactKind.PARAMS, path="p.yaml", hasher="yaml-fields"),
        "model": Artifact(
            id="model", kind=ArtifactKind.MODEL, path="m.json", hasher="model", derived_from=("params",)
        ),
    }
    reqs = {
        "R": Requirement(
            id="R",
            text="t",
            quantity="q",
            op=Comparator.LE,
            limit=80.0,
            unit="degC",
            criticality=Criticality.HIGH,
        )
    }
    f: dict[str, Any] = {
        "manifest_hash": "mh",
        "quantities": {"q": "degC", "r": "mm"},
        "artifacts": arts,
        "versions": {"params": ArtifactVersion(artifact_id="params", content_hash="h")},
        "assumptions": {"A": Assumption(id="A", statement="s", variable="v", unit="degC", bounds=(1, 2))},
        "requirements": reqs,
        "subjects": {"S": Subject(id="S", kind=SubjectKind.DESIGN)},
        "claims": {
            "C": Claim(id="C", requirement_id="R", subject_id="S"),
            "C2": Claim(id="C2", requirement_id="R", subject_id="S", policy_id="low"),
        },
        "policies": dict(DEFAULT_POLICIES),
        "producers": {},
    }
    if reverse:
        f = {k: (dict(reversed(list(v.items()))) if isinstance(v, dict) else v) for k, v in f.items()}
    return f


def test_id_stable_under_insertion_order_and_ignores_git_rev() -> None:
    a = Snapshot.create(**_fields())
    b = Snapshot.create(**_fields(reverse=True))
    c = Snapshot.create(**_fields(), git_rev="abc123")
    assert a.id == b.id == c.id == content_id(a, exclude=frozenset({"id", "git_rev"}))
    assert c.git_rev == "abc123"
    assert Snapshot(**{**_fields(), "id": a.id, "git_rev": "zzz"}).id == a.id


def test_id_changes_with_content() -> None:
    a = Snapshot.create(**_fields())
    assert Snapshot.create(**{**_fields(), "manifest_hash": "other"}).id != a.id


def test_wrong_id_raises() -> None:
    with pytest.raises(ValidationError):
        Snapshot(**{**_fields(), "id": "0" * 64})


def test_policy_for() -> None:
    s = Snapshot.create(**_fields())
    assert s.policy_for("C") == DEFAULT_POLICIES["high"]
    assert s.policy_for("C2") == DEFAULT_POLICIES["low"]


def test_json_round_trip_all_models() -> None:
    s = Snapshot.create(**_fields())
    req = EvidenceRequirement(kind="measurement")  # type: ignore[arg-type]
    objs: list[BaseModel] = [
        s,
        Change(
            kind=ChangeKind.ROWS_ADDED,
            target="d[x]",
            groups=("g",),
            columns=("x",),
            rows_bbox={"x": (0.0, 1.0)},
            detail="d",
        ),
        ChangeSet(
            from_snapshot="a",
            to_snapshot="b",
            changes=(Change(kind=ChangeKind.FIELD_CHANGED, target="p#/a", old=1, new=2, delta=1.0),),
        ),
        Reason(code=ReasonCode.POLICY_SATISFIED, message="m", evidence_ids=("e",), detail={"k": [1]}),
        EvidenceUse(
            evidence_id="e",
            verdict=Verdict.PASS,
            freshness=FreshnessClass.CARRY_FORWARD,
            interval_used=Interval(lo=1.0, hi=2.0, unit="K"),
            derived_from_evidence="e0",
            recorded_verdict=Verdict.PASS,
        ),
        Assessment(
            claim_id="C", snapshot_id=s.id, status=Status.SUPPORTED, reasons=(), evidence=(), input_hash="h"
        ),
        Obligation(claim_id="C", clause_index=0, conjunct_index=1, requirement=req),
        CandidateRun(id="p@S", producer_id="p", subject_id="S", cost=1.0, satisfies=("C/0/0",)),
        PlanningProblem(
            snapshot_id=s.id,
            claim_weights={"C": 3},
            clauses={"C": (("C/0/0",),)},
            obligations={
                "C/0/0": Obligation(claim_id="C", clause_index=0, conjunct_index=0, requirement=req)
            },
            candidates=(),
            incompatible=(("a", "b", "c", "d"),),
        ),
        PlannedRun(candidate_id="p@S", producer_id="p", subject_id="S", cost=1.0, discharges=("C/0/0",)),
        RevalidationPlan(
            id="i",
            snapshot_id=s.id,
            planner="ilp",
            objective="min_cost",
            runs=(),
            total_cost=0.0,
            chosen_clauses={"C": 0},
            unrestorable=(),
            solver_status="OPTIMAL",
        ),
    ]
    for o in objs:
        assert type(o).model_validate_json(o.model_dump_json()) == o
        assert type(o).model_validate(o.model_dump()) == o


def test_obligation_key() -> None:
    o = Obligation(
        claim_id="C", clause_index=2, conjunct_index=1, requirement=EvidenceRequirement(kind="analytic")
    )  # type: ignore[arg-type]
    assert o.key == "C/2/1"
