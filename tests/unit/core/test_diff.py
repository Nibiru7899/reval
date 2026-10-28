"""P3-01: snapshot diff -> ChangeSet (docs/10 §4.2), built from mini-project snapshots."""

from typing import Any

from reval.core.diff import diff_snapshots
from reval.domain.changes import Change, ChangeKind, ChangeSet
from reval.domain.evidence import ProducerKind
from reval.domain.policies import EvidenceRequirement, Policy
from tests.helpers.mini_fresh import append, edit, pid, resnap

K = ChangeKind


def _kinds(cs: ChangeSet) -> list[tuple[ChangeKind, str]]:
    return [(c.kind, c.target) for c in cs.changes]


def _one(cs: ChangeSet, kind: ChangeKind) -> Change:
    (c,) = [c for c in cs.changes if c.kind is kind]
    return c


def test_identical_snapshots_give_empty_changeset(mini: Any) -> None:
    s = mini.snapshot()
    cs = diff_snapshots(s, s)
    assert cs.changes == ()
    assert cs.from_snapshot == cs.to_snapshot == s.id


def test_field_changed_with_delta(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(mini, "params/params.yaml", "scale: 1.0", "scale: 1.05")
    cs = diff_snapshots(s0, mini.snapshot())
    assert _kinds(cs) == [(K.FIELD_CHANGED, "params#/load/scale")]
    c = cs.changes[0]
    assert (c.old, c.new) == (1.0, 1.05)
    assert c.delta is not None and abs(c.delta - 0.05) < 1e-12


def test_field_changed_non_numeric_has_no_delta(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(mini, "params/params.yaml", "gain: 2.0", "gain: high")
    c = _one(diff_snapshots(s0, mini.snapshot()), K.FIELD_CHANGED)
    assert (c.old, c.new, c.delta) == (2.0, "high", None)


def test_bool_field_has_no_delta(mini: Any) -> None:
    edit(mini, "params/params.yaml", "gain: 2.0", "gain: true")
    s0 = mini.snapshot()
    edit(mini, "params/params.yaml", "gain: true", "gain: false")
    c = _one(diff_snapshots(s0, mini.snapshot()), K.FIELD_CHANGED)
    assert (c.old, c.new, c.delta) == (True, False, None)


def test_field_added_and_removed(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(mini, "params/params.yaml", "  gain: 2.0", "  offset: 3")
    cs = diff_snapshots(s0, mini.snapshot())
    assert _kinds(cs) == [(K.FIELD_ADDED, "params#/sim/offset"), (K.FIELD_REMOVED, "params#/sim/gain")]
    assert _one(cs, K.FIELD_ADDED).new == 3
    assert _one(cs, K.FIELD_REMOVED).old == 2.0


def _csv_rows(group: str, xs: list[float]) -> str:
    return "".join(f"{group},{x},{20 + 10 * x}\n" for x in xs)


def test_rows_added_one_change_with_new_bbox(mini: Any) -> None:
    s0 = mini.snapshot()
    append(mini, "data/data.csv", _csv_rows("g4", [5.0, 5.5]) + _csv_rows("g5", [6.0]))
    cs = diff_snapshots(s0, mini.snapshot())
    c = _one(cs, K.ROWS_ADDED)
    assert c.target == "data[group,temp,x]"
    assert c.groups == ("g4", "g5")
    assert c.rows_bbox == {"temp": (70.0, 80.0), "x": (5.0, 6.0)}
    # The surrogate folds the data hash (D3), so it changes too.
    assert (K.ARTIFACT_CHANGED, "surrogate") in _kinds(cs)


def test_rows_removed_uses_old_bbox(mini: Any) -> None:
    s0 = mini.snapshot()
    path = mini.root / "data" / "data.csv"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text("".join(ln for ln in lines if not ln.startswith("g3,")), encoding="utf-8")
    c = _one(diff_snapshots(s0, mini.snapshot()), K.ROWS_REMOVED)
    assert c.groups == ("g3",)
    assert c.rows_bbox == {"temp": (19.5, 39.5), "x": (0.0, 1.9)}


def test_rows_modified_columns_and_old_new_hull(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(mini, "data/data.csv", "g2,1.9,39.5", "g2,1.9,45.0")
    cs = diff_snapshots(s0, mini.snapshot())
    c = _one(cs, K.ROWS_MODIFIED)
    assert c.target == "data[temp]"
    assert c.columns == ("temp",)
    assert c.groups == ("g2",)
    assert c.rows_bbox == {"temp": (19.5, 45.0), "x": (0.0, 1.9)}


def test_rows_modified_hull_includes_old_bbox(mini: Any) -> None:
    s0 = mini.snapshot()
    path = mini.root / "data" / "data.csv"
    text = path.read_text(encoding="utf-8")
    # Shift every g1 row to x in [10, 11.9]: the hull still covers the old bbox.
    lines = []
    for ln in text.splitlines():
        if ln.startswith("g1,"):
            _, x, t = ln.split(",")
            ln = f"g1,{float(x) + 10:.1f},{t}"
        lines.append(ln)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    c = _one(diff_snapshots(s0, mini.snapshot()), K.ROWS_MODIFIED)
    assert c.columns == ("x",)
    assert c.rows_bbox is not None
    assert c.rows_bbox["x"] == (0.0, 11.9)


def test_column_set_change_is_artifact_changed(mini: Any) -> None:
    s0 = mini.snapshot()
    path = mini.root / "data" / "data.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0] + ",y"] + [ln + ",1" for ln in lines[1:]]) + "\n", encoding="utf-8")
    cs = diff_snapshots(s0, mini.snapshot())
    c = [c for c in cs.changes if c.target == "data"]
    assert len(c) == 1 and c[0].kind is K.ARTIFACT_CHANGED
    assert c[0].detail == "column set changed: +y"
    assert not [c for c in cs.changes if c.kind in (K.ROWS_ADDED, K.ROWS_MODIFIED, K.ROWS_REMOVED)]


def test_model_change_is_artifact_changed(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(mini, "models/surrogate.json", '"slope": 10.0', '"slope": 11.0')
    assert _kinds(diff_snapshots(s0, mini.snapshot())) == [(K.ARTIFACT_CHANGED, "surrogate")]


def test_artifact_removed_and_added_via_missing(mini: Any) -> None:
    s0 = mini.snapshot()
    model = mini.root / "models" / "surrogate.json"
    body = model.read_text(encoding="utf-8")
    model.unlink()
    s1 = mini.snapshot()
    assert _kinds(diff_snapshots(s0, s1)) == [(K.ARTIFACT_REMOVED, "surrogate")]
    model.write_text(body, encoding="utf-8")
    assert _kinds(diff_snapshots(s1, mini.snapshot())) == [(K.ARTIFACT_ADDED, "surrogate")]


def test_artifact_entry_added_and_removed(mini: Any) -> None:
    s0 = mini.snapshot()
    (mini.root / "params" / "extra.yaml").write_text("k: 1\n", encoding="utf-8")
    edit(
        mini,
        "reval.yaml",
        "  params: {kind: params, path: params/params.yaml}",
        "  params: {kind: params, path: params/params.yaml}\n"
        "  extra: {kind: params, path: params/extra.yaml}",
    )
    s1 = mini.snapshot()
    assert _kinds(diff_snapshots(s0, s1)) == [(K.ARTIFACT_ADDED, "extra")]
    assert _kinds(diff_snapshots(s1, s0)) == [(K.ARTIFACT_REMOVED, "extra")]


def test_requirement_limit_change_has_old_new_delta(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(mini, "reval.yaml", 'op: "<=", limit: 30.05', 'op: "<=", limit: 30.1')
    c = _one(diff_snapshots(s0, mini.snapshot()), K.REQUIREMENT_CHANGED)
    assert c.target == "R-SHAFT"
    assert (c.old, c.new) == (30.05, 30.1)
    assert c.delta is not None and abs(c.delta - 0.05) < 1e-9


def test_assumption_and_subject_changed(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(mini, "reval.yaml", "bounds: [10, 40]", "bounds: [10, 45]")
    edit(mini, "reval.yaml", "load: [2.0, 3.9]", "load: [2.0, 3.8]")
    cs = diff_snapshots(s0, mini.snapshot())
    assert _kinds(cs) == [(K.ASSUMPTION_CHANGED, "A-ambient"), (K.SUBJECT_CHANGED, "S2")]


def test_claim_added_and_removed(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(
        mini,
        "reval.yaml",
        "  - {id: C-SHAFT, requirement: R-SHAFT, subject: D1}",
        "  - {id: C-SHAFT, requirement: R-SHAFT, subject: D1}\n"
        "  - {id: C-S2-HI, requirement: R-TEMP-HI, subject: S2}",
    )
    s1 = mini.snapshot()
    c = _one(diff_snapshots(s0, s1), K.CLAIM_CHANGED)
    assert (c.target, c.detail) == ("C-S2-HI", "added")
    assert _one(diff_snapshots(s1, s0), K.CLAIM_CHANGED).detail == "removed"


def test_policy_changed(mini: Any) -> None:
    s0 = mini.snapshot()
    low = Policy(id="low", alternatives=((EvidenceRequirement(kind=ProducerKind.MEASUREMENT),),))
    s1 = resnap(s0, policies={**s0.policies, "low": low})
    assert _kinds(diff_snapshots(s0, s1)) == [(K.POLICY_CHANGED, "low")]


def test_producer_code_changed(mini: Any) -> None:
    s0 = mini.snapshot()
    p = pid(mini, "sim_temp")
    prod = s0.producers[p].model_copy(update={"code_hash": "f" * 64})
    s1 = resnap(s0, producers={**s0.producers, p: prod})
    assert _kinds(diff_snapshots(s0, s1)) == [(K.PRODUCER_CODE_CHANGED, p)]
    deps = s0.producers[p].model_copy(update={"depends_on": ("params#/load/scale",)})
    s2 = resnap(s0, producers={**s0.producers, p: deps})
    assert _kinds(diff_snapshots(s0, s2)) == [(K.PRODUCER_CODE_CHANGED, p)]


def test_unclassifiable_is_unknown(mini: Any) -> None:
    s0 = mini.snapshot()
    s1 = resnap(s0, quantities={**s0.quantities, "temp_peak": "K"})
    c = _one(diff_snapshots(s0, s1), K.UNKNOWN)
    assert c.target == "quantity:temp_peak"
    # A version that differs without any classifiable field difference.
    v = s0.versions["params"].model_copy(update={"content_hash": "0" * 64})
    s2 = resnap(s0, versions={**s0.versions, "params": v})
    assert _kinds(diff_snapshots(s0, s2)) == [(K.UNKNOWN, "params")]


def test_output_sorted_and_deterministic(mini: Any) -> None:
    s0 = mini.snapshot()
    edit(mini, "params/params.yaml", "scale: 1.0", "scale: 1.1")
    edit(mini, "params/params.yaml", "d_mm: 30.00", "d_mm: 30.02")
    edit(mini, "reval.yaml", "bounds: [10, 40]", "bounds: [10, 45]")
    append(mini, "data/data.csv", _csv_rows("g4", [5.0]))
    s1 = mini.snapshot()
    a, b = diff_snapshots(s0, s1), diff_snapshots(s0, s1)
    assert a == b
    keys = [(c.kind.value, c.target) for c in a.changes]
    assert keys == sorted(keys)
    assert len(a.changes) == 5
