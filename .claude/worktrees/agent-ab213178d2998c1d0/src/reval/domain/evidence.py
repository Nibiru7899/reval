"""Evidence, producers, tolerances, waivers (docs/10-interfaces.md §2, docs/03 §2)."""

import math
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import model_validator

from reval.core.canonical import content_id
from reval.domain.base import Frozen
from reval.domain.quantities import Interval
from reval.domain.selectors import Selector


class ProducerKind(StrEnum):
    ML_PREDICTION = "ml_prediction"
    PHYSICS_SIM = "physics_sim"
    MEASUREMENT = "measurement"
    ANALYTIC = "analytic"
    WAIVER = "waiver"


DEFAULT_FIDELITY: dict[ProducerKind, int] = {
    ProducerKind.ML_PREDICTION: 1,
    ProducerKind.PHYSICS_SIM: 2,
    ProducerKind.MEASUREMENT: 3,
    ProducerKind.ANALYTIC: 3,
    ProducerKind.WAIVER: 0,
}


class Producer(Frozen):
    """Metadata of a registered evidence producer."""

    id: str
    kind: ProducerKind
    quantities: tuple[str, ...]
    fidelity: int
    cost: float
    code_hash: str
    depends_on: tuple[str, ...]
    assumes: tuple[str, ...] = ()
    predictors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.kind is ProducerKind.WAIVER:
            if self.cost < 0:
                raise ValueError("cost must be >= 0")
        elif not self.cost > 0:
            raise ValueError("cost must be > 0")
        dep_artifacts = {Selector.parse(s).artifact_id for s in self.depends_on}
        missing = sorted(set(self.predictors) - dep_artifacts)
        if missing:
            raise ValueError(f"predictors {missing} must also appear as artifacts in depends_on")
        return self


class Dependency(Frozen):
    selector: str
    version_hash: str


class Scope(Frozen):
    box: dict[str, tuple[float, float]] = {}  # noqa: RUF012  (pydantic copies defaults)
    assumption_ids: tuple[str, ...] = ()


class Tolerance(Frozen):
    """Declared sensitivity of an output to a params field; kappa is applied once, at inflation."""

    selector: str
    sensitivity: float
    input_unit: str
    output_unit: str
    valid_range: tuple[float, float]
    safety_factor: float = 1.5
    source: str
    assumption_id: str

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not (math.isfinite(self.sensitivity) and self.sensitivity >= 0):
            raise ValueError("sensitivity must be finite and >= 0")
        if not (math.isfinite(self.safety_factor) and self.safety_factor >= 1):
            raise ValueError("safety_factor must be >= 1")
        if not self.source.strip():
            raise ValueError("source must be non-empty")
        if not self.assumption_id:
            raise ValueError("assumption_id is required")
        if Selector.parse(self.selector).pointer is None:
            raise ValueError("tolerance selector must be a pointer selector (art#/ptr)")
        lo, hi = self.valid_range
        if not (math.isfinite(lo) and math.isfinite(hi) and lo <= hi):
            raise ValueError("valid_range must be finite with lo <= hi")
        return self


class Provenance(Frozen):
    producer_code_hash: str
    snapshot_id: str
    env: dict[str, str] = {}  # noqa: RUF012  (pydantic copies defaults)
    seed: int | None = None


class EvidenceResult(Frozen):
    quantity: str
    unit: str
    point: float | None = None
    interval: Interval | None = None
    uncertainty_kind: Literal["conformal", "sensor", "model_form", "exact", "none"] = "none"
    in_domain: bool | None = None
    domain_report: dict[str, Any] | None = None


class Waiver(Frozen):
    author: str
    justification: str
    claim_id: str
    requirement_hash: str

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.justification.strip():
            raise ValueError("waiver justification must be non-empty")
        if not self.claim_id:
            raise ValueError("waiver claim_id must be non-empty")
        if not self.requirement_hash:
            raise ValueError("waiver requirement_hash must be non-empty")
        return self


class Evidence(Frozen):
    """One recorded result. ``id == content_id(self)``; no timestamps, so the id is pure content."""

    id: str
    producer_id: str
    producer_kind: ProducerKind
    fidelity: int
    subject_id: str
    result: EvidenceResult
    deps: tuple[Dependency, ...]
    scope: Scope = Scope()
    tolerances: tuple[Tolerance, ...] = ()
    provenance: Provenance
    cost: float
    derived_from_evidence: str | None = None
    waiver: Waiver | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.producer_kind is ProducerKind.WAIVER) != (self.waiver is not None):
            raise ValueError("waiver is required iff producer_kind is WAIVER")
        expected = content_id(self)
        if self.id != expected:
            raise ValueError(f"evidence id {self.id!r} != content_id {expected!r}")
        return self

    @classmethod
    def create(cls, **fields: Any) -> Self:
        """Build an Evidence with its id computed from the other fields."""
        draft = cls.model_construct(id="", **fields)
        return cls(**{**fields, "id": content_id(draft)})
