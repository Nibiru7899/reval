"""Artifacts and their recorded versions (docs/10-interfaces.md §2)."""

from enum import StrEnum
from typing import Literal

from reval.domain.base import Frozen


class ArtifactKind(StrEnum):
    DATASET = "dataset"
    MODEL = "model"
    PARAMS = "params"
    CODE = "code"
    DOCUMENT = "document"


class Artifact(Frozen):
    """A tracked file. ``derived_from`` is the constructive trace (artifact ids)."""

    id: str
    kind: ArtifactKind
    path: str
    hasher: Literal["file", "yaml-fields", "dataframe", "model"]
    derived_from: tuple[str, ...] = ()
    key: tuple[str, ...] = ()


class RowGroupInfo(Frozen):
    n_rows: int
    bbox: dict[str, tuple[float, float]]


class ArtifactVersion(Frozen):
    """Hashes of an artifact at one snapshot; ``content_hash == "missing"`` if the file is absent."""

    artifact_id: str
    content_hash: str
    field_hashes: dict[str, str] = {}  # noqa: RUF012  (pydantic copies defaults)
    field_values: dict[str, float | int | str | bool | None] = {}  # noqa: RUF012  (pydantic copies defaults)
    row_groups: dict[str, RowGroupInfo] = {}  # noqa: RUF012  (pydantic copies defaults)
