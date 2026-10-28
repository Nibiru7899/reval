"""P5-09: baselines B1-B4 on the mini project."""

from pathlib import Path

import pytest

from bench.baselines import (
    FileLevel,
    NaiveTrust,
    OodOnly,
    PostState,
    PreState,
    RandomBudget,
    execute_baseline,
)
from bench.harness.cache import ProducerResultCache
from tests.bench._mini import copy_mini, edit, open_project


def _states(tmp_path: Path, field: tuple[str, str, str]):  # type: ignore[no-untyped-def]
    root = copy_mini(tmp_path)
    proj = open_project(root)
    snap = proj.snapshot()
    proj.run_all()
    pre = PreState.capture(root, snap, proj.store.list_evidence())
    edit(root, *field)
    post_proj = open_project(root)
    return pre, post_proj, PostState(post_proj, post_proj.snapshot())


@pytest.fixture
def cache(tmp_path: Path) -> ProducerResultCache:
    return ProducerResultCache(tmp_path / "cache")


def test_b1_reruns_strictly_more_than_reval_for_single_field_change(tmp_path: Path) -> None:
    pre, post_proj, post = _states(tmp_path, ("params/params.yaml", "gain: 2.0", "gain: 2.1"))
    b1 = FileLevel().select_runs(pre, post)
    plan = post_proj.plan(post.snapshot)
    assert len(b1) > len(plan.runs)
    # whole-file hashing cannot tell the shaft diameter apart from the gain
    assert ("shaft_check", "D1") in {(p.split(":")[-1], s) for p, s in b1}
    assert not any(p.endswith("measure_temp") for p, _ in b1)  # reads only data.csv, which is unchanged


def test_b1_unchanged_project_reruns_nothing(tmp_path: Path) -> None:
    pre, _, post = _states(tmp_path, ("params/params.yaml", "gain: 2.0", "gain: 2.0"))
    assert FileLevel().select_runs(pre, post) == []


def test_b3_costs_zero_and_keeps_old_support(tmp_path: Path, cache: ProducerResultCache) -> None:
    pre, _, post = _states(tmp_path, ("params/params.yaml", "gain: 2.0", "gain: 2.1"))
    res = execute_baseline(NaiveTrust(), pre, post, cache)
    assert res.runs == () and res.cost == 0.0
    assert {e.id for e in res.evidence} == {e.id for e in pre.evidence}


def test_b4_is_deterministic_and_within_budget(tmp_path: Path, cache: ProducerResultCache) -> None:
    pre, _, post = _states(tmp_path, ("params/params.yaml", "gain: 2.0", "gain: 2.1"))
    a = RandomBudget("scn-1", 5.0).select_runs(pre, post)
    assert a == RandomBudget("scn-1", 5.0).select_runs(pre, post)
    assert sum(post.snapshot.producers[p].cost for p, _ in a) <= 5.0
    assert RandomBudget("scn-1", 0.0).select_runs(pre, post) == []
    res = execute_baseline(RandomBudget("scn-1", 5.0), pre, post, cache)
    assert res.cost <= 5.0
    # a larger budget selects at least as many runs
    assert len(RandomBudget("scn-1", 100.0).select_runs(pre, post)) >= len(a)


def test_b2_reruns_only_ml_that_is_out_of_domain(tmp_path: Path, cache: ProducerResultCache) -> None:
    pre, _, post = _states(tmp_path, ("params/params.yaml", "gain: 2.0", "gain: 2.1"))
    inside_all = OodOnly(lambda p, pid, sid: True)
    assert inside_all.select_runs(pre, post) == []
    ood = OodOnly(lambda p, pid, sid: sid != "S2")
    runs = ood.select_runs(pre, post)
    assert runs and all(sid == "S2" and pid.endswith("predict_temp") for pid, sid in runs)
    res = execute_baseline(ood, pre, post, cache)
    assert res.cost == 1.0
