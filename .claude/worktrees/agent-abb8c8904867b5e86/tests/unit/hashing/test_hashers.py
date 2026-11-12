from pathlib import Path

import pandas as pd
import pytest

from reval.core.selectors import selector_hash
from reval.domain import Artifact, ArtifactKind, ArtifactVersion
from reval.hashing import HASHERS, hash_artifact


def _art(id: str, kind: ArtifactKind, path: str, hasher: str, **kw: object) -> Artifact:
    return Artifact(id=id, kind=kind, path=path, hasher=hasher, **kw)  # type: ignore[arg-type]


def test_registry_keys() -> None:
    assert set(HASHERS) == {"file", "yaml-fields", "dataframe", "model"}


def test_missing_file(tmp_path: Path) -> None:
    for h in HASHERS:
        a = _art("x", ArtifactKind.DOCUMENT, "nope.bin", h, key=("g",))
        assert hash_artifact(a, tmp_path, {}).content_hash == "missing"


def test_file_hash_changes_with_bytes(tmp_path: Path) -> None:
    a = _art("f", ArtifactKind.DOCUMENT, "f.txt", "file")
    (tmp_path / "f.txt").write_bytes(b"one")
    h1 = hash_artifact(a, tmp_path, {})
    (tmp_path / "f.txt").write_bytes(b"two")
    h2 = hash_artifact(a, tmp_path, {})
    assert h1.content_hash != h2.content_hash
    assert h1.field_hashes == {}


def test_yaml_leaf_change_changes_exactly_one_field(tmp_path: Path) -> None:
    a = _art("p", ArtifactKind.PARAMS, "p.yaml", "yaml-fields")
    p = tmp_path / "p.yaml"
    p.write_text("shaft:\n  d_mm: 40\n  l_mm: 100\nload:\n  scale: 1.0\n  steps: [1, 2]\n")
    v1 = hash_artifact(a, tmp_path, {})
    p.write_text("shaft:\n  d_mm: 42\n  l_mm: 100\nload:\n  scale: 1.0\n  steps: [1, 2]\n")
    v2 = hash_artifact(a, tmp_path, {})
    changed = {k for k in v1.field_hashes if v1.field_hashes[k] != v2.field_hashes[k]}
    assert changed == {"/shaft/d_mm"}
    assert set(v1.field_hashes) == {
        "/shaft/d_mm",
        "/shaft/l_mm",
        "/load/scale",
        "/load/steps/0",
        "/load/steps/1",
    }
    assert v2.field_values["/shaft/d_mm"] == 42
    assert v1.content_hash != v2.content_hash


def test_yaml_pointer_format_matches_selector_hash(tmp_path: Path) -> None:
    from reval.domain import Snapshot

    a = _art("params", ArtifactKind.PARAMS, "p.yaml", "yaml-fields")
    (tmp_path / "p.yaml").write_text("a/b:\n  c: 1\nd:\n  e: 2\n")
    v = hash_artifact(a, tmp_path, {})
    assert "/a~1b/c" in v.field_hashes
    snap = Snapshot.create(
        manifest_hash="m", quantities={}, artifacts={"params": a}, versions={"params": v},
        assumptions={}, requirements={}, subjects={}, claims={}, policies={}, producers={},
    )  # fmt: skip
    assert selector_hash(snap, "params#/d") != "missing"
    assert selector_hash(snap, "params#/d/e") != selector_hash(snap, "params#/a~1b")


def _write_csv(path: Path, rows: list[tuple[str, float, float]]) -> None:
    pd.DataFrame(rows, columns=["g", "temp", "speed"]).to_csv(path, index=False)


def test_dataframe_group_column_hashes(tmp_path: Path) -> None:
    a = _art("d", ArtifactKind.DATASET, "d.csv", "dataframe", key=("g", "t"))
    base = [("a", 1.0, 10.0), ("a", 2.0, 11.0), ("b", 3.0, 12.0), ("b", 4.0, 13.0)]
    _write_csv(tmp_path / "d.csv", base)
    v1 = hash_artifact(a, tmp_path, {})
    assert v1.row_groups["a"].n_rows == 2
    assert v1.row_groups["b"].bbox["temp"] == (3.0, 4.0)

    _write_csv(tmp_path / "d.csv", [("a", 1.0, 10.0), ("a", 2.5, 11.0), *base[2:]])
    v2 = hash_artifact(a, tmp_path, {})
    changed = {k for k in v1.field_hashes if v1.field_hashes[k] != v2.field_hashes[k]}
    assert changed == {"g=a/c=temp", "c=temp"}
    assert v1.content_hash != v2.content_hash


def test_dataframe_row_order_matters(tmp_path: Path) -> None:
    # Time series: reordering rows within a profile is a real change.
    a = _art("d", ArtifactKind.DATASET, "d.csv", "dataframe", key=("g",))
    _write_csv(tmp_path / "d.csv", [("a", 1.0, 1.0), ("a", 2.0, 2.0)])
    v1 = hash_artifact(a, tmp_path, {})
    _write_csv(tmp_path / "d.csv", [("a", 2.0, 2.0), ("a", 1.0, 1.0)])
    v2 = hash_artifact(a, tmp_path, {})
    assert v1.content_hash != v2.content_hash


def test_dataframe_group_order_does_not_matter(tmp_path: Path) -> None:
    a = _art("d", ArtifactKind.DATASET, "d.csv", "dataframe", key=("g",))
    _write_csv(tmp_path / "d.csv", [("a", 1.0, 1.0), ("b", 2.0, 2.0)])
    v1 = hash_artifact(a, tmp_path, {})
    _write_csv(tmp_path / "d.csv", [("b", 2.0, 2.0), ("a", 1.0, 1.0)])
    assert hash_artifact(a, tmp_path, {}).content_hash == v1.content_hash


def test_dataframe_requires_key(tmp_path: Path) -> None:
    a = _art("d", ArtifactKind.DATASET, "d.csv", "dataframe")
    _write_csv(tmp_path / "d.csv", [("a", 1.0, 1.0)])
    with pytest.raises(ValueError, match="key"):
        hash_artifact(a, tmp_path, {})


def test_dataframe_parquet(tmp_path: Path) -> None:
    a = _art("d", ArtifactKind.DATASET, "d.parquet", "dataframe", key=("g",))
    pd.DataFrame({"g": [1, 1, 2], "x": [1.0, 2.0, 3.0]}).to_parquet(tmp_path / "d.parquet")
    v = hash_artifact(a, tmp_path, {})
    assert {"g=1/c=x", "g=2/c=x", "c=x"} <= set(v.field_hashes)


def test_upstream_folding_model_and_params(tmp_path: Path) -> None:
    (tmp_path / "m.bin").write_bytes(b"model")
    (tmp_path / "lptn.yaml").write_text("k: 1\n")
    model = _art("model", ArtifactKind.MODEL, "m.bin", "model", derived_from=("data",))
    params = _art("lptn", ArtifactKind.PARAMS, "lptn.yaml", "yaml-fields", derived_from=("data",))
    up1 = {"data": ArtifactVersion(artifact_id="data", content_hash="h1")}
    up2 = {"data": ArtifactVersion(artifact_id="data", content_hash="h2")}
    for art in (model, params):
        a = hash_artifact(art, tmp_path, up1)
        b = hash_artifact(art, tmp_path, up2)
        assert a.content_hash != b.content_hash  # file unchanged
        assert a.field_hashes == b.field_hashes  # field hashes stay own-only
        plain = hash_artifact(art.model_copy(update={"derived_from": ()}), tmp_path, {})
        assert plain.content_hash != a.content_hash


def test_upstream_missing_raises(tmp_path: Path) -> None:
    (tmp_path / "m.bin").write_bytes(b"x")
    m = _art("m", ArtifactKind.MODEL, "m.bin", "model", derived_from=("data",))
    with pytest.raises(ValueError, match="upstream"):
        hash_artifact(m, tmp_path, {})
