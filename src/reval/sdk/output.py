"""Producer return types and result helpers (docs/10 §7)."""

from typing import Any

from reval.domain.base import Frozen
from reval.domain.evidence import EvidenceResult, Scope, Tolerance, Waiver
from reval.domain.quantities import Interval


class ProducerOutput(Frozen):
    """What a producer function returns; the runner turns it into Evidence."""

    results: tuple[EvidenceResult, ...]
    scope: Scope = Scope()
    tolerances: tuple[Tolerance, ...] = ()
    waiver: Waiver | None = None


def interval_result(
    quantity: str,
    unit: str,
    point: float,
    lo: float,
    hi: float,
    *,
    uncertainty_kind: str,
    in_domain: bool | None = None,
    domain_report: dict[str, Any] | None = None,
) -> EvidenceResult:
    """Result with a point estimate and an uncertainty interval in ``unit`` (canonical unit)."""
    return EvidenceResult.model_validate(
        {
            "quantity": quantity,
            "unit": unit,
            "point": point,
            "interval": Interval(lo=lo, hi=hi, unit=unit),
            "uncertainty_kind": uncertainty_kind,
            "in_domain": in_domain,
            "domain_report": domain_report,
        }
    )


def exact_result(quantity: str, unit: str, value: float) -> EvidenceResult:
    """Exact value. The interval is the degenerate [value, value] so inflation has something to widen."""
    return interval_result(quantity, unit, value, value, value, uncertainty_kind="exact")
