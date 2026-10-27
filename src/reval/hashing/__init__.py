"""Artifact hashers (adapter layer; reads files). Contract: docs/10 §6."""

from collections.abc import Mapping
from pathlib import Path

from reval.domain.artifacts import Artifact, ArtifactVersion
from reval.hashing.base import Hasher
from reval.hashing.dataframe import hash_dataframe
from reval.hashing.file import hash_file
from reval.hashing.model import hash_model
from reval.hashing.yaml_fields import hash_yaml_fields

HASHERS: dict[str, Hasher] = {
    "file": hash_file,
    "yaml-fields": hash_yaml_fields,
    "dataframe": hash_dataframe,
    "model": hash_model,
}


def hash_artifact(artifact: Artifact, root: Path, upstream: Mapping[str, ArtifactVersion]) -> ArtifactVersion:
    """Hash ``artifact`` with its declared hasher; ``upstream`` maps derived_from ids to their versions."""
    return HASHERS[artifact.hasher](artifact, root, upstream)


__all__ = ["HASHERS", "Hasher", "hash_artifact"]
