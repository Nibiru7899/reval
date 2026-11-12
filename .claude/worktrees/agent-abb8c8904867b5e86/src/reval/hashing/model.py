"""``model`` hasher: file bytes plus upstream folding (docs/10 §6)."""

from collections.abc import Mapping
from pathlib import Path

from reval.domain.artifacts import Artifact, ArtifactVersion
from reval.hashing.file import hash_file


def hash_model(artifact: Artifact, root: Path, upstream: Mapping[str, ArtifactVersion]) -> ArtifactVersion:
    """Same as ``file``; kept separate so upstream folding makes an untrained-but-stale model invalid."""
    return hash_file(artifact, root, upstream)
