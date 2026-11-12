"""Manifest loader: fixture project, error reporting, unit conversion, references, cycles."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from reval.errors import ManifestError
from reval.manifest import load_manifest, manifest_hash

MINI = Path(__file__).resolve().parents[2] / "fixtures" / "mini_project"


def _write(tmp_path: Path, mutate: Callable[[dict[str, Any]], None] | None = None) -> Path:
    raw = yaml.safe_load((MINI / "reval.yaml").read_text(encoding="utf-8"))
    if mutate is not None:
        mutate(raw)
    p = tmp_path / "reval.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return p


def test_mini_project_loads() -> None:
    m = load_manifest(MINI / "reval.yaml")
    assert set(m.artifacts) == {"params", "data", "surrogate"}
    assert m.artifacts["surrogate"].derived_from == ("data",)
    assert [c.id for c in m.claims] == ["C-S1-TEMP", "C-S2-TEMP", "C-S1-HI", "C-SHAFT"]
    assert m.requirements["R-SHAFT"].limit == 30.05
    assert m.producers == ("mini.producers",)


def test_manifest_hash_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    h = manifest_hash(MINI / "reval.yaml")
    assert h == manifest_hash(MINI / "reval.yaml") and len(h) == 64
    changed = _write(tmp_path, lambda r: r["requirements"]["R-TEMP"].update(limit=81))
    assert manifest_hash(changed) != h


def test_unknown_key_names_the_key(tmp_path: Path) -> None:
    p = _write(tmp_path, lambda r: r["requirements"]["R-TEMP"].update(bogus_key=1))
    with pytest.raises(ManifestError, match="bogus_key") as ei:
        load_manifest(p)
    assert ei.value.location is not None and "R-TEMP" in ei.value.location


def test_fahrenheit_limit_converts_exactly(tmp_path: Path) -> None:
    p = _write(tmp_path, lambda r: r["requirements"]["R-TEMP"].update(limit=176, unit="degF"))
    m = load_manifest(p)
    assert m.requirements["R-TEMP"].limit == 80.0
    assert m.requirements["R-TEMP"].unit == "degC"


def test_incompatible_unit_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, lambda r: r["requirements"]["R-TEMP"].update(unit="mm"))
    with pytest.raises(ManifestError, match="not convertible"):
        load_manifest(p)


def test_unknown_unit_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, lambda r: r["requirements"]["R-TEMP"].update(unit="florps"))
    with pytest.raises(ManifestError, match="unknown unit"):
        load_manifest(p)


def test_claim_with_missing_references_raises(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="R-NOPE"):
        load_manifest(_write(tmp_path, lambda r: r["claims"][0].update(requirement="R-NOPE")))
    with pytest.raises(ManifestError, match="S9"):
        load_manifest(_write(tmp_path, lambda r: r["claims"][0].update(subject="S9")))
    with pytest.raises(ManifestError, match="nopol"):
        load_manifest(_write(tmp_path, lambda r: r["claims"][0].update(policy="nopol")))


def test_derived_from_cycle_and_missing_artifact_raise(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="cycle"):
        load_manifest(_write(tmp_path, lambda r: r["artifacts"]["data"].update(derived_from=["surrogate"])))
    with pytest.raises(ManifestError, match="ghost"):
        load_manifest(_write(tmp_path, lambda r: r["artifacts"]["data"].update(derived_from=["ghost"])))


def test_subjects_file(tmp_path: Path) -> None:
    def to_file(r: dict[str, Any]) -> None:
        (tmp_path / "subjects.yaml").write_text(yaml.safe_dump(r.pop("subjects")), encoding="utf-8")
        r["subjects_file"] = "subjects.yaml"

    m = load_manifest(_write(tmp_path, to_file))
    assert set(m.subjects) == {"S1", "S2", "D1"}


def test_invalid_yaml_and_missing_file(tmp_path: Path) -> None:
    bad = tmp_path / "reval.yaml"
    bad.write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(bad)
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "nope.yaml")


def test_wrong_version_and_policy_override(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="version"):
        load_manifest(_write(tmp_path, lambda r: r.update(version=2)))
    m = load_manifest(_write(tmp_path, lambda r: r.update(policies={"custom": [[{"kind": "measurement"}]]})))
    assert m.policies["custom"][0][0].kind.value == "measurement"


def test_manifest_error_is_backward_compatible() -> None:
    assert str(ManifestError("plain")) == "plain"
    e = ManifestError("m", path="p.yaml", location="a.b")
    assert str(e) == "p.yaml: a.b: m" and e.location == "a.b"
