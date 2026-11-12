"""P3-06: Project.assess/diff classify stored evidence against the changes since it was produced."""

from pathlib import Path

import pytest

from reval.domain import FreshnessClass, Status
from reval.gitio import snapshot_at_rev
from reval.services import Project
from tests.helpers.gitrepo import make_repo

F = FreshnessClass


@pytest.fixture
def small_change(root: Path) -> Path:
    return make_repo(root, "1.05")


def _by_producer(proj: Project, freshness: dict[str, object]) -> dict[tuple[str, str], FreshnessClass]:
    out: dict[tuple[str, str], FreshnessClass] = {}
    for e in proj.store.list_evidence():
        out[(e.producer_id.rsplit(":", 1)[1], e.subject_id)] = freshness[e.id].cls  # type: ignore[attr-defined]
    return out


def test_small_change_carries_sim_and_invalidates_predict(small_change: Path) -> None:
    proj = Project.open(small_change)
    a = snapshot_at_rev(small_change, "HEAD~1")
    b = snapshot_at_rev(small_change, "HEAD")
    report = proj.diff(a, b)
    fr = _by_producer(proj, report.freshness)
    assert fr[("sim_temp", "S1")] is F.CARRY_FORWARD
    assert fr[("sim_temp", "S2")] is F.CARRY_FORWARD
    assert fr[("predict_temp", "S1")] is F.INVALIDATED
    assert fr[("shaft_check", "D1")] is F.FRESH_EXACT
    assert "C-SHAFT" not in report.affected_claims
    assert "C-S1-TEMP" in report.affected_claims
    assert report.after["C-SHAFT"].status is Status.SUPPORTED
    # the original evidence is untouched: carried items are never stored (D5)
    assert all(e.derived_from_evidence is None for e in proj.store.list_evidence())


def test_diff_stores_nothing_but_assess_appends_a_batch(small_change: Path) -> None:
    proj = Project.open(small_change)
    n = len(proj.store.list_evidence())
    a = snapshot_at_rev(small_change, "HEAD~1")
    b = snapshot_at_rev(small_change, "HEAD")
    proj.diff(a, b)
    assert proj.store.latest_assessed_snapshot() is None or proj.store.latest_assessed_snapshot() != b.id
    assessments = proj.assess(b)
    assert len(proj.store.list_evidence()) == n
    assert proj.store.get_assessments(b.id) == assessments


def test_unchanged_snapshot_is_fully_fresh_exact(root: Path) -> None:
    proj = Project.open(root)
    proj.run_all()
    snap = proj.snapshot()
    before = proj.assess(snap)
    report = proj.diff(snap, snap)
    assert report.changes.changes == ()
    assert {f.cls for f in report.freshness.values()} == {F.FRESH_EXACT}
    assert report.affected_claims == ()
    assert report.after == before == report.before


def test_missing_old_snapshot_invalidates(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = Project.open(root)
    evidence = proj.run_all()
    monkeypatch.setenv("REVAL_DATABASE_URL", "sqlite://")  # a store that never saw the evidence's snapshot
    other = Project.open(root)
    for e in evidence:
        other.store.put_evidence(e)
    params = root / "params" / "params.yaml"
    params.write_text(
        params.read_text(encoding="utf-8").replace("scale: 1.0", "scale: 1.05"), encoding="utf-8"
    )
    live = other.snapshot()
    assert other.store.get_snapshot(evidence[0].provenance.snapshot_id) is None
    out = other.assess(live)
    assert Status.SUPPORTED not in {a.status for a in out.values()}
    assert Status.VIOLATED not in {a.status for a in out.values()}
