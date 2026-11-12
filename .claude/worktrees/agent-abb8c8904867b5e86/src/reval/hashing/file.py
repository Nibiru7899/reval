"""Byte-level hashers: ``file`` and ``model`` (docs/10 §6)."""

from collections.abc import Mapping
from pathlib import Path

from reval.core.canonical import sha256_hex
from reval.domain.artifacts import Artifact, ArtifactVersion
from reval.hashing.base import MISSING, fold_upstream, resolve


def hash_file(artifact: Artifact, root: Path, upstream: Mapping[str, ArtifactVersion]) -> ArtifactVersion:
    """sha256 of the file bytes; no fields."""
    path = resolve(artifact, root)
    if path is None:
        return ArtifactVersion(artifact_id=artifact.id, content_hash=MISSING)
    own = sha256_hex(path.read_bytes())
    return ArtifactVersion(artifact_id=artifact.id, content_hash=fold_upstream(artifact, own, upstream))
