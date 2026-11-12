"""Snapshot: the complete hashed state of a project at one moment (docs/10-interfaces.md §2)."""

from typing import Any, Self

from pydantic import model_validator

from reval.core.canonical import content_id
from reval.domain.artifacts import Artifact, ArtifactVersion
from reval.domain.base import Frozen
from reval.domain.engineering import Assumption, Claim, Requirement, Subject
from reval.domain.evidence import Producer
from reval.domain.policies import Policy

_ID_EXCLUDE = frozenset({"id", "git_rev"})


class Snapshot(Frozen):
    """``id`` is the content hash of everything except ``id`` and the informational ``git_rev``."""

    id: str
    git_rev: str | None = None
    manifest_hash: str
    quantities: dict[str, str]
    artifacts: dict[str, Artifact]
    versions: dict[str, ArtifactVersion]
    assumptions: dict[str, Assumption]
    requirements: dict[str, Requirement]
    subjects: dict[str, Subject]
    claims: dict[str, Claim]
    policies: dict[str, Policy]
    producers: dict[str, Producer]

    @model_validator(mode="after")
    def _check_id(self) -> Self:
        expected = content_id(self, exclude=_ID_EXCLUDE)
        if self.id != expected:
            raise ValueError(f"snapshot id {self.id!r} != content_id {expected!r}")
        return self

    @classmethod
    def create(cls, **fields: Any) -> Self:
        """Build a Snapshot with its id computed from the other fields."""
        draft = cls.model_construct(id="", **fields)
        return cls(**{**fields, "id": content_id(draft, exclude=_ID_EXCLUDE)})

    def policy_for(self, claim_id: str) -> Policy:
        """Policy of a claim: its ``policy_id`` or, by default, its requirement's criticality."""
        claim = self.claims[claim_id]
        policy_id = claim.policy_id or self.requirements[claim.requirement_id].criticality.value
        return self.policies[policy_id]
