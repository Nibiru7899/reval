"""Hasher protocol and the shared upstream-folding rule (docs/10 §6, D3)."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from reval.core.canonical import sha256_hex
from reval.domain.artifacts import Artifact, ArtifactVersion

MISSING = "missing"


class Hasher(Protocol):
    """Computes the ArtifactVersion of one artifact; ``upstream`` holds its ``derived_from`` versions."""

    def __call__(
        self, artifact: Artifact, root: Path, upstream: Mapping[str, ArtifactVersion]
    ) -> ArtifactVersion: ...


def fold_upstream(artifact: Artifact, own: str, upstream: Mapping[str, ArtifactVersion]) -> str:
    """Fold upstream content hashes into ``own`` so a stale derived artifact is detected (fail closed).

    A derived file (e.g. params identified from a dataset) must change its hash when its source changes,
    even if nobody regenerated it. A missing upstream entry is a caller bug, never silently ignored.
    """
    if not artifact.derived_from:
        return own
    parts = []
    for up_id in sorted(artifact.derived_from):
        if up_id not in upstream:
            raise ValueError(f"artifact {artifact.id!r}: upstream version {up_id!r} was not provided")
        parts.append(upstream[up_id].content_hash)
    return sha256_hex("|".join([own, *parts]).encode("utf-8"))


def resolve(artifact: Artifact, root: Path) -> Path | None:
    """Absolute path of the artifact's file, or None if it does not exist."""
    path = root / artifact.path
    return path if path.is_file() else None
