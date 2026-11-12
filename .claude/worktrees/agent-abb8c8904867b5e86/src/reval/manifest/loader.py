"""Load and validate reval.yaml. Does not import producer modules."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from reval.core.canonical import canonical_json, sha256_hex
from reval.domain.engineering import Assumption
from reval.domain.policies import DEFAULT_POLICIES
from reval.errors import ManifestError
from reval.manifest.schema import ManifestModel, RequirementSpec
from reval.manifest.units import convert, validate_unit


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ManifestError(f"cannot read file: {exc}", path=path) from exc
    except yaml.YAMLError as exc:
        raise ManifestError(f"invalid YAML: {exc}", path=path) from exc


def _parsed(path: Path) -> dict[str, Any]:
    """Parsed manifest with ``subjects_file`` resolved into ``subjects`` (so the hash covers it)."""
    raw = _read_yaml(path)
    if not isinstance(raw, dict):
        raise ManifestError("top level must be a mapping", path=path)
    raw = dict(raw)
    sf = raw.pop("subjects_file", None)
    if sf is not None:
        if "subjects" in raw:
            raise ManifestError(
                "give either 'subjects' or 'subjects_file', not both", path=path, location="subjects_file"
            )
        if not isinstance(sf, str):
            raise ManifestError("subjects_file must be a path string", path=path, location="subjects_file")
        sub = _read_yaml(path.parent / sf)
        if not isinstance(sub, dict):
            raise ManifestError("subjects file must be a mapping of id -> subject", path=path.parent / sf)
        raw["subjects"] = sub
    return raw


def manifest_hash(path: Path) -> str:
    """sha256 of canonical_json(parsed YAML); includes the subjects file content when one is used."""
    try:
        return sha256_hex(canonical_json(_parsed(Path(path))))
    except ValueError as exc:  # NaN / inf in YAML
        raise ManifestError(str(exc), path=path) from exc


def _fmt_loc(loc: tuple[Any, ...]) -> str:
    return ".".join(str(p) for p in loc)


def _find_cycle(graph: dict[str, tuple[str, ...]]) -> list[str] | None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(n: str) -> list[str] | None:
        state[n] = 1
        stack.append(n)
        for m in graph.get(n, ()):
            if state.get(m, 0) == 1:
                return [*stack[stack.index(m) :], m]
            if state.get(m, 0) == 0 and (c := visit(m)) is not None:
                return c
        stack.pop()
        state[n] = 2
        return None

    for node in sorted(graph):
        if state.get(node, 0) == 0 and (c := visit(node)) is not None:
            return c
    return None


def load_manifest(path: Path) -> ManifestModel:
    """Parse, validate and unit-normalise a manifest; raises ManifestError (path, location) on any problem."""
    path = Path(path)
    raw = _parsed(path)
    try:
        m = ManifestModel.model_validate(raw)
    except ValidationError as exc:
        errors = exc.errors()
        msg = "; ".join(f"{_fmt_loc(e['loc'])}: {e['msg']}" for e in errors)
        raise ManifestError(msg, path=path, location=_fmt_loc(errors[0]["loc"])) from exc

    def fail(msg: str, loc: str) -> ManifestError:
        return ManifestError(msg, path=path, location=loc)

    for q, u in m.quantities.items():
        try:
            validate_unit(u, location=f"quantities.{q}")
        except ManifestError as exc:
            raise fail(exc.message, f"quantities.{q}") from exc
    for aid, a in m.assumptions.items():
        try:
            validate_unit(a.unit)
            Assumption(id=aid, **a.model_dump())
        except (ManifestError, ValueError) as exc:
            raise fail(str(exc), f"assumptions.{aid}") from exc

    converted: dict[str, RequirementSpec] = {}
    for rid, r in m.requirements.items():
        loc = f"requirements.{rid}"
        if r.quantity not in m.quantities:
            raise fail(f"unknown quantity {r.quantity!r}", f"{loc}.quantity")
        canonical = m.quantities[r.quantity]
        try:
            validate_unit(r.unit)
            limit = convert(r.limit, r.unit, canonical)
        except ManifestError as exc:
            raise fail(exc.message, f"{loc}.unit") from exc
        converted[rid] = r.model_copy(update={"limit": limit, "unit": canonical})

    for art_id, art in m.artifacts.items():
        for up in art.derived_from:
            if up not in m.artifacts:
                raise fail(
                    f"derived_from refers to unknown artifact {up!r}", f"artifacts.{art_id}.derived_from"
                )
    cyc = _find_cycle({art_id: art.derived_from for art_id, art in m.artifacts.items()})
    if cyc is not None:
        raise fail("derived_from cycle: " + " -> ".join(cyc), f"artifacts.{cyc[0]}.derived_from")

    seen: set[str] = set()
    for i, c in enumerate(m.claims):
        loc = f"claims[{i}]"
        if c.id in seen:
            raise fail(f"duplicate claim id {c.id!r}", f"{loc}.id")
        seen.add(c.id)
        if c.requirement not in m.requirements:
            raise fail(
                f"claim {c.id!r} refers to unknown requirement {c.requirement!r}", f"{loc}.requirement"
            )
        if c.subject not in m.subjects:
            raise fail(f"claim {c.id!r} refers to unknown subject {c.subject!r}", f"{loc}.subject")
        if c.policy is not None and c.policy not in m.policies and c.policy not in DEFAULT_POLICIES:
            raise fail(f"claim {c.id!r} refers to unknown policy {c.policy!r}", f"{loc}.policy")

    return m.model_copy(update={"requirements": converted})
