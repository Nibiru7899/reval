"""P3-04: the out-of-scope row excuse (docs/10 §4.3 step 3, D12): fires only under its stated condition."""

from typing import Any

from reval.core.diff import diff_snapshots
from reval.core.freshness import FreshnessResult, classify_evidence
from reval.core.selectors import selector_hash
from reval.domain.artifacts import ArtifactKind
from reval.domain.changes import ChangeKind, ChangeSet
from reval.domain.evidence import Dependency, Evidence, Scope
from reval.domain.snapshot import Snapshot
from reval.domain.status import FreshnessClass
from tests.helpers.mini_fresh import append, reev, resnap, run

F = FreshnessClass
K = ChangeKind
IN_RANGE = {"x": (0.0, 1.9)}  # the recorded x range of every group


def _scoped(e: Evidence, box: dict[str, tuple[float, float]]) -> Evidence:
    return reev(e, scope=Scope(box=box, assumption_ids=e.scope.assumption_ids))


def _classify(e: Evidence, old: Snapshot, new: Snapshot) -> FreshnessResult:
    return classify_evidence(e, old, new, diff_snapshots(old, new))


def _rows(group: str, xs: list[float]) -> str:
    return "".join(f"{group},{x},{20 + 10 * x}\n" for x in xs)


def test_disjoint_rows_out_of_scope_overlapping_invalidated(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = _scoped(run(mini, s0, "measure_temp", "S1"), IN_RANGE)
    append(mini, "data/data.csv", _rows("g4", [5.0, 6.0]))
    s1 = mini.snapshot()
    fr = _classify(meas, s0, s1)
    assert (fr.cls, fr.inflation, fr.reasons) == (F.FRESH_OUT_OF_SCOPE, 0.0, ())
    assert [c.kind for c in fr.relevant_changes] == [K.ROWS_ADDED]

    append(mini, "data/data.csv", _rows("g5", [1.0, 1.5]))
    assert _classify(meas, s0, mini.snapshot()).cls is F.INVALIDATED


def test_touching_interval_is_not_disjoint(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = _scoped(run(mini, s0, "measure_temp", "S1"), {"x": (0.0, 5.0)})
    append(mini, "data/data.csv", _rows("g4", [5.0, 6.0]))
    assert _classify(meas, s0, mini.snapshot()).cls is F.INVALIDATED


def test_empty_box_never_qualifies(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = run(mini, s0, "measure_temp", "S1")
    assert meas.scope.box == {}
    append(mini, "data/data.csv", _rows("g4", [5.0, 6.0]))
    assert _classify(meas, s0, mini.snapshot()).cls is F.INVALIDATED


def test_box_without_shared_variable_never_qualifies(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = _scoped(run(mini, s0, "measure_temp", "S1"), {"ambient": (10.0, 40.0)})
    append(mini, "data/data.csv", _rows("g4", [5.0, 6.0]))
    assert _classify(meas, s0, mini.snapshot()).cls is F.INVALIDATED


def test_whole_artifact_data_dep_invalidated(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = run(mini, s0, "measure_temp", "S1")
    whole = reev(
        meas,
        deps=(Dependency(selector="data", version_hash=selector_hash(s0, "data")),),
        scope=Scope(box=IN_RANGE),
    )
    append(mini, "data/data.csv", _rows("g4", [5.0, 6.0]))
    assert _classify(whole, s0, mini.snapshot()).cls is F.INVALIDATED


def test_surrogate_derived_evidence_invalidated_even_out_of_scope(mini: Any) -> None:
    s0 = mini.snapshot()
    ml = _scoped(run(mini, s0, "predict_temp", "S1"), IN_RANGE)
    append(mini, "data/data.csv", _rows("g4", [5.0, 6.0]))
    fr = _classify(ml, s0, mini.snapshot())
    assert fr.cls is F.INVALIDATED
    assert {c.kind for c in fr.relevant_changes} == {K.ROWS_ADDED, K.ARTIFACT_CHANGED}


def _shift_g1(mini: Any, by: float) -> None:
    path = mini.root / "data" / "data.csv"
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("g1,"):
            _, x, t = ln.split(",")
            ln = f"g1,{float(x) + by:.1f},{t}"
        out.append(ln)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def test_rows_modified_old_overlaps_new_disjoint_invalidated(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = run(mini, s0, "measure_temp", "S1")
    # Depend on x as well, so the x-only modification is relevant.
    meas = reev(
        meas,
        deps=(Dependency(selector="data[temp,x]", version_hash=selector_hash(s0, "data[temp,x]")),),
        scope=Scope(box={"x": (0.0, 5.0)}),
    )
    _shift_g1(mini, 10.0)  # old g1 x in [0, 1.9] overlaps the box, new x in [10, 11.9] does not
    fr = _classify(meas, s0, mini.snapshot())
    assert [c.kind for c in fr.relevant_changes] == [K.ROWS_MODIFIED]
    assert fr.cls is F.INVALIDATED


def test_rows_modified_both_sides_disjoint_out_of_scope(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = run(mini, s0, "measure_temp", "S1")
    meas = reev(
        meas,
        deps=(Dependency(selector="data[temp,x]", version_hash=selector_hash(s0, "data[temp,x]")),),
        scope=Scope(box={"x": (50.0, 60.0)}),
    )
    _shift_g1(mini, 10.0)
    assert _classify(meas, s0, mini.snapshot()).cls is F.FRESH_OUT_OF_SCOPE


def test_modified_column_outside_dep_columns_is_irrelevant(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = run(mini, s0, "measure_temp", "S1")  # depends on data[temp] only
    _shift_g1(mini, 10.0)  # only x changes
    fr = _classify(meas, s0, mini.snapshot())
    assert fr.cls is F.FRESH_EXACT


def test_missing_rows_bbox_never_qualifies(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = _scoped(run(mini, s0, "measure_temp", "S1"), IN_RANGE)
    append(mini, "data/data.csv", _rows("g4", [5.0, 6.0]))
    s1 = mini.snapshot()
    cs = diff_snapshots(s0, s1)
    stripped = tuple(c.model_copy(update={"rows_bbox": None}) for c in cs.changes)
    fr = classify_evidence(meas, s0, s1, ChangeSet(from_snapshot=s0.id, to_snapshot=s1.id, changes=stripped))
    assert fr.cls is F.INVALIDATED


def test_column_dep_on_non_dataset_never_qualifies(mini: Any) -> None:
    s0 = mini.snapshot()
    meas = _scoped(run(mini, s0, "measure_temp", "S1"), IN_RANGE)
    append(mini, "data/data.csv", _rows("g4", [5.0, 6.0]))
    s1 = mini.snapshot()
    as_model = {**s1.artifacts, "data": s1.artifacts["data"].model_copy(update={"kind": ArtifactKind.MODEL})}
    s0m = resnap(
        s0,
        artifacts={
            **s0.artifacts,
            "data": s0.artifacts["data"].model_copy(update={"kind": ArtifactKind.MODEL}),
        },
    )
    s1m = resnap(s1, artifacts=as_model)
    meas_m = reev(meas, provenance=meas.provenance.model_copy(update={"snapshot_id": s0m.id}))
    cs = diff_snapshots(s0m, s1m)
    assert K.ROWS_ADDED in {c.kind for c in cs.changes}
    assert classify_evidence(meas_m, s0m, s1m, cs).cls is F.INVALIDATED
