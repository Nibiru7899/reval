from pathlib import Path
from typing import Any

import pytest

from reval.domain import (
    Assessment,
    Dependency,
    Evidence,
    EvidenceResult,
    PlannedRun,
    ProducerKind,
    Provenance,
    RevalidationPlan,
    Snapshot,
    Status,
)
from reval.errors import StoreError
from reval.store import Job, JobState, SqlStore, open_store


@pytest.fixture
def store() -> SqlStore:
    return SqlStore("sqlite://")


def _snap(tag: str = "m", git_rev: str | None = None) -> Snapshot:
    return Snapshot.create(
        manifest_hash=tag, quantities={}, artifacts={}, versions={}, assumptions={}, requirements={},
        subjects={}, claims={}, policies={}, producers={}, git_rev=git_rev,
    )  # fmt: skip


def _ev(subject: str = "S1", point: float = 1.0, snap: str = "s") -> Evidence:
    return Evidence.create(
        producer_id="m:p",
        producer_kind=ProducerKind.ML_PREDICTION,
        fidelity=1,
        subject_id=subject,
        result=EvidenceResult(quantity="q", unit="degC", point=point),
        deps=(Dependency(selector="a", version_hash="h"),),
        provenance=Provenance(producer_code_hash="c", snapshot_id=snap),
        cost=1.0,
    )


def _asm(snap: str, claim: str = "C1", status: Status = Status.SUPPORTED) -> Assessment:
    return Assessment(
        claim_id=claim,
        snapshot_id=snap,
        status=status,
        reasons=(),
        evidence=(),
        input_hash="ih",
    )


def _plan(snap: str, pid: str) -> RevalidationPlan:
    return RevalidationPlan(
        id=pid, snapshot_id=snap, planner="greedy", objective="min_cost",
        runs=(PlannedRun(candidate_id="c", producer_id="p", subject_id="S", cost=1.0, discharges=()),),
        total_cost=1.0, chosen_clauses={"C": 0}, unrestorable=(), solver_status="ok",
    )  # fmt: skip


def test_snapshot_roundtrip_and_idempotence(store: SqlStore) -> None:
    s1, s2 = _snap("a"), _snap("b")
    store.put_snapshot(s1)
    store.put_snapshot(s2)
    store.put_snapshot(s1)
    assert store.get_snapshot(s1.id) == s1
    assert store.get_snapshot("nope") is None
    assert store.list_snapshots() == (s1, s2)


def test_snapshot_same_content_other_git_rev_is_noop(store: SqlStore) -> None:
    a, b = _snap("a", "rev1"), _snap("a", "rev2")
    assert a.id == b.id
    store.put_snapshot(a)
    store.put_snapshot(b)
    got = store.get_snapshot(a.id)
    assert got is not None and got.git_rev == "rev1"


def test_evidence_roundtrip_filter_and_conflict(store: SqlStore) -> None:
    e1, e2 = _ev("S1"), _ev("S2", 2.0)
    store.put_evidence(e1)
    store.put_evidence(e2)
    store.put_evidence(e1)  # no-op
    assert store.list_evidence() == (e1, e2)
    assert store.list_evidence(subject_id="S2") == (e2,)
    assert store.list_evidence(subject_id="zz") == ()


def test_evidence_same_id_different_body_raises(store: SqlStore) -> None:
    e = _ev()
    store.put_evidence(e)
    forged = e.model_copy(update={"cost": 99.0})  # model_copy skips the id validator
    with pytest.raises(StoreError):
        store.put_evidence(forged)


def test_assessment_batches_are_append_only(store: SqlStore) -> None:
    s = _snap()
    assert store.get_assessments(s.id) == {}
    assert store.put_assessments(s.id, [_asm(s.id, "C1"), _asm(s.id, "C2")]) == 1
    assert store.put_assessments(s.id, [_asm(s.id, "C1", Status.STALE)]) == 2
    latest = store.get_assessments(s.id)
    assert set(latest) == {"C1"} and latest["C1"].status is Status.STALE
    first = store.get_assessments(s.id, seq=1)
    assert set(first) == {"C1", "C2"} and first["C1"].status is Status.SUPPORTED


def test_assessment_validation(store: SqlStore) -> None:
    with pytest.raises(StoreError):
        store.put_assessments("s1", [_asm("other")])
    with pytest.raises(StoreError):
        store.put_assessments("s1", [_asm("s1"), _asm("s1")])


def test_latest_assessed_snapshot_follows_batch_order(store: SqlStore) -> None:
    assert store.latest_assessed_snapshot() is None
    store.put_assessments("A", [_asm("A")])
    store.put_assessments("B", [_asm("B")])
    assert store.latest_assessed_snapshot() == "B"
    assert store.latest_assessed_snapshot(before="B") == "A"
    assert store.latest_assessed_snapshot(before="A") is None
    store.put_assessments("A", [_asm("A", status=Status.STALE)])  # revisit the old snapshot
    assert store.latest_assessed_snapshot() == "A"
    assert store.latest_assessed_snapshot(before="A") == "B"
    assert store.latest_assessed_snapshot(before="never") == "A"


def test_plans(store: SqlStore) -> None:
    p1, p2 = _plan("s", "p1"), _plan("s", "p2")
    assert store.latest_plan("s") is None
    store.put_plan(p1)
    store.put_plan(p2)
    store.put_plan(p1)
    assert store.get_plan("p1") == p1
    assert store.latest_plan("s") == p2
    with pytest.raises(StoreError):
        store.put_plan(p1.model_copy(update={"total_cost": 5.0}))


def test_jobs_lifecycle(store: SqlStore) -> None:
    job = Job(id="j1", kind="run", state=JobState.QUEUED, payload={"producer": "p", "n": 1})
    store.put_job(job)
    assert store.get_job("j1") == job
    with pytest.raises(StoreError):
        store.put_job(job)
    store.update_job_state("j1", JobState.RUNNING)
    got = store.get_job("j1")
    assert got is not None and got.state is JobState.RUNNING and got.result is None
    store.update_job_state("j1", JobState.SUCCEEDED, result={"evidence": ["e1"]})
    got = store.get_job("j1")
    assert got == job.model_copy(update={"state": JobState.SUCCEEDED, "result": {"evidence": ["e1"]}})
    with pytest.raises(StoreError):
        store.update_job_state("zz", JobState.FAILED)
    assert store.get_job("zz") is None


def test_reports(store: SqlStore) -> None:
    body: dict[str, Any] = {"a": 1, "b": [1, 2], "c": {"d": "x"}}
    store.put_report("r1", "s", body)
    store.put_report("r1", "s", dict(reversed(list(body.items()))))  # same content, other key order
    assert store.get_report("r1") == body
    assert store.get_report("none") is None
    with pytest.raises(StoreError):
        store.put_report("r1", "s", {"a": 2})


def test_open_store_creates_db_and_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REVAL_DATABASE_URL", raising=False)
    s = _snap()
    st = open_store(tmp_path)
    st.put_snapshot(s)
    st.close()
    assert (tmp_path / ".reval" / "reval.db").is_file()
    st2 = open_store(tmp_path)
    assert st2.get_snapshot(s.id) == s
    st2.close()


def test_open_store_env_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVAL_DATABASE_URL", "sqlite://")
    st = open_store(tmp_path)
    st.put_report("r", "s", {})
    assert st.get_report("r") == {}
    assert not (tmp_path / ".reval").exists()
