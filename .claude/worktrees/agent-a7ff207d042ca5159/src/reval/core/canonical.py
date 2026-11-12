"""Canonical JSON and content hashing (docs/10-interfaces.md §1.2-1.3). Pure: json, hashlib, math only."""

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any


def _to_jsonable(obj: object) -> Any:
    # Duck-typed so core never imports pydantic or the domain package.
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError(f"non-finite float cannot be canonicalised: {obj}")
    if isinstance(obj, Mapping):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        return sorted((_to_jsonable(v) for v in obj), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def canonical_json(obj: object) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace, NaN/inf rejected (ValueError)."""
    return json.dumps(
        _to_jsonable(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 digest (64 chars)."""
    return hashlib.sha256(data).hexdigest()


def content_id(obj: object, *, exclude: frozenset[str] = frozenset({"id"})) -> str:
    """sha256_hex(canonical_json(obj without excluded top-level keys))."""
    data = _to_jsonable(obj)
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k not in exclude}
    return sha256_hex(canonical_json(data))


def difference_unit(unit: str) -> str:
    """Unit of differences of a quantity: `degC` -> `K`, otherwise unchanged."""
    return "K" if unit == "degC" else unit
