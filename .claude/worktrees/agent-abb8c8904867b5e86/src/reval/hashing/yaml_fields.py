"""``yaml-fields`` hasher: per-leaf RFC 6901 pointers (docs/10 §6)."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from reval.core.canonical import canonical_json, sha256_hex
from reval.domain.artifacts import Artifact, ArtifactVersion
from reval.hashing.base import MISSING, fold_upstream, resolve


def _escape(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _flatten(node: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(node, dict) and node:
        for k, v in node.items():
            _flatten(v, f"{prefix}/{_escape(str(k))}", out)
    elif isinstance(node, list) and node:
        for i, v in enumerate(node):
            _flatten(v, f"{prefix}/{i}", out)
    else:
        out[prefix] = node  # scalars and empty containers are leaves


def hash_yaml_fields(
    artifact: Artifact, root: Path, upstream: Mapping[str, ArtifactVersion]
) -> ArtifactVersion:
    """Hash every leaf of a YAML document; scalar leaves are also kept in ``field_values``."""
    path = resolve(artifact, root)
    if path is None:
        return ArtifactVersion(artifact_id=artifact.id, content_hash=MISSING)
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    leaves: dict[str, Any] = {}
    _flatten(doc, "", leaves)
    field_hashes = {ptr: sha256_hex(canonical_json(v)) for ptr, v in leaves.items()}
    field_values = {
        ptr: v for ptr, v in leaves.items() if v is None or isinstance(v, (bool, int, float, str))
    }
    own = sha256_hex(canonical_json(doc))
    return ArtifactVersion(
        artifact_id=artifact.id,
        content_hash=fold_upstream(artifact, own, upstream),
        field_hashes=field_hashes,
        field_values=field_values,
    )
