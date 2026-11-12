"""Pydantic mirror of reval.yaml (docs/10 §3.1). Unknown keys are rejected everywhere."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from reval.domain.artifacts import ArtifactKind
from reval.domain.engineering import Comparator, Criticality, SubjectKind
from reval.domain.policies import EvidenceRequirement


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactSpec(_Strict):
    kind: ArtifactKind
    path: str
    hasher: Literal["file", "yaml-fields", "dataframe", "model"] | None = None
    derived_from: tuple[str, ...] = ()
    key: tuple[str, ...] = ()


class AssumptionSpec(_Strict):
    statement: str
    variable: str
    unit: str
    bounds: tuple[float, float] | None = None
    value: float | None = None
    tol: float | None = None


class RequirementSpec(_Strict):
    text: str
    quantity: str
    op: Comparator
    limit: float
    unit: str
    criticality: Criticality


class SubjectSpec(_Strict):
    kind: SubjectKind
    generator: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ClaimSpec(_Strict):
    id: str
    requirement: str
    subject: str
    policy: str | None = None


class ManifestModel(_Strict):
    """A loaded manifest. Requirement limits are already converted to the quantity's canonical unit."""

    version: Literal[1]
    project: str
    quantities: dict[str, str]
    artifacts: dict[str, ArtifactSpec] = Field(default_factory=dict)
    assumptions: dict[str, AssumptionSpec] = Field(default_factory=dict)
    requirements: dict[str, RequirementSpec] = Field(default_factory=dict)
    subjects: dict[str, SubjectSpec] = Field(default_factory=dict)
    claims: tuple[ClaimSpec, ...] = ()
    policies: dict[str, tuple[tuple[EvidenceRequirement, ...], ...]] = Field(default_factory=dict)
    producers: tuple[str, ...] = ()
