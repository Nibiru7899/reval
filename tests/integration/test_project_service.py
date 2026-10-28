"""P2-11: Project service and lock file on a private copy of the mini project."""

from pathlib import Path

import pytest

from reval.domain import FreshnessClass, Status
from reval.errors import LockNotFoundError, StoreError
from reval.gitio import LOCK_FILE, parse_lock, read_lock, write_lock
from reval.services import Project

EXPECTED = {
    "C-S1-TEMP": Status.SUPPORTED,
    "C-S2-TEMP": Status.VIOLATED,
    "C-S1-HI": Status.SUPPORTED,
    "C-SHAFT": Status.SUPPORTED,
}


def _statuses(p: Project) -> dict[str, Status]:
    return {cid: a.status for cid, a in p.assess().items()}


def test_no_evidence_is_inconclusive(root: Path) -> None:
    assert set(_statuses(Project.open(root)).values()) == {Status.INCONCLUSIVE}


def test_run_all_then_assess_matches_expected(root: Path) -> None:
    p = Project.open(root)
    evidence = p.run_all()
    assert len(evidence) == 6  # EXPECTED.md: six producer x subject rows
    assessments = p.assess()
    assert {c: a.status for c, a in assessments.items()} == EXPECTED
    assert assessments["C-S1-TEMP"].satisfied_clause == 0
    assert assessments["C-SHAFT"].satisfied_clause == 3


def test_run_all_twice_adds_no_duplicate_evidence(root: Path) -> None:
    p = Project.open(root)
    p.run_all()
    n = len(p.store.list_evidence())
    p.run_all()
    assert len(p.store.list_evidence()) == n == 6


def test_assess_appends_batches(root: Path) -> None:
    p = Project.open(root)
    p.run_all()
    p.assess()
    snap = p.snapshot()
    p.assess(snap)
    assert p.store.get_assessments(snap.id)  # latest batch readable
    assert p.store.latest_assessed_snapshot() == snap.id


def test_single_run(root: Path) -> None:
    p = Project.open(root)
    (e,) = p.run("mini.producers:shaft_check", "D1")
    assert e.subject_id == "D1" and e.result.point == 30.0


def test_editing_load_scale_invalidates_temperature_not_shaft(root: Path) -> None:
    p = Project.open(root)
    p.run_all()
    params = root / "params" / "params.yaml"
    params.write_text(
        params.read_text(encoding="utf-8").replace("scale: 1.0", "scale: 1.1"), encoding="utf-8"
    )
    after = Project.open(root).assess()
    fresh = {u.evidence_id: u.freshness for a in after.values() for u in a.evidence}
    by_producer = {e.id: e.producer_id.split(":")[1] for e in p.store.list_evidence()}
    state = {(by_producer[i], f) for i, f in fresh.items()}
    assert ("shaft_check", FreshnessClass.FRESH_EXACT) in state
    assert ("measure_temp", FreshnessClass.FRESH_EXACT) in state  # depends on data only
    assert ("sim_temp", FreshnessClass.INVALIDATED) in state
    assert ("predict_temp", FreshnessClass.INVALIDATED) in state
    assert after["C-SHAFT"].status is Status.SUPPORTED
    assert after["C-S1-TEMP"].satisfied_clause == 1  # measurement alone; the ML+physics clause is gone
    assert after["C-S1-HI"].status is Status.SUPPORTED
    assert after["C-S2-TEMP"].status is Status.STALE  # the only FAIL (physics) was invalidated: rule 3


def test_lock_is_deterministic_and_round_trips(root: Path) -> None:
    p = Project.open(root)
    snap = p.snapshot(write_lock=True)
    path = root / LOCK_FILE
    first = path.read_bytes()
    assert b"\r" not in first and first.endswith(b"\n")
    assert Project.open(root).snapshot(write_lock=True) == snap
    assert path.read_bytes() == first
    assert read_lock(path) == snap
    assert parse_lock(first, "x") == snap


def test_lock_ignores_git_rev(root: Path) -> None:
    snap = Project.open(root).snapshot()
    path = write_lock(root, snap.model_copy(update={"git_rev": "abc123"}))
    assert b'"git_rev": null' in path.read_bytes()
    assert read_lock(path).id == snap.id


def test_hand_edited_lock_raises_store_error(root: Path) -> None:
    snap = Project.open(root).snapshot(write_lock=True)
    path = root / LOCK_FILE
    path.write_text(path.read_text(encoding="utf-8").replace(snap.manifest_hash, "0" * 64), encoding="utf-8")
    with pytest.raises(StoreError):
        read_lock(path)


def test_garbage_lock_raises_store_error(tmp_path: Path) -> None:
    bad = tmp_path / LOCK_FILE
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(StoreError):
        read_lock(bad)


def test_missing_lock_raises_lock_not_found(tmp_path: Path) -> None:
    with pytest.raises(LockNotFoundError):
        read_lock(tmp_path / LOCK_FILE)
