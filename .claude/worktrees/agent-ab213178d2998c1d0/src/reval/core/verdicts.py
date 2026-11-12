"""Evidence verdicts (docs/03-domain-model.md §2, docs/10-interfaces.md §4.4). Pure."""

from reval.domain.assessment import Reason
from reval.domain.engineering import Comparator, Requirement
from reval.domain.evidence import Evidence, ProducerKind
from reval.domain.status import ReasonCode, Verdict


def verdict_interval(e: Evidence) -> tuple[float, float] | None:
    """The ``[lo, hi]`` a verdict uses: the result interval, or ``[point, point]`` for exact results."""
    if e.result.interval is not None:
        return e.result.interval.lo, e.result.interval.hi
    if e.result.uncertainty_kind == "exact" and e.result.point is not None:
        return e.result.point, e.result.point
    return None


def verdict(e: Evidence, req: Requirement) -> tuple[Verdict, tuple[Reason, ...]]:
    """Reduce one evidence item to PASS / FAIL / INCONCLUSIVE against ``req``.

    Bounds are inclusive on the pass side (``hi <= L`` passes for ``<=``, ``lo > L`` fails).
    Raises ``ValueError`` on a quantity or unit mismatch: the manifest loader canonicalises units,
    so a mismatch here is a programming error, never something to paper over.
    """
    res = e.result
    if res.quantity != req.quantity:
        raise ValueError(
            f"evidence {e.id} is for quantity {res.quantity!r}, requirement {req.id} for {req.quantity!r}"
        )
    if res.unit != req.unit or (res.interval is not None and res.interval.unit != req.unit):
        raise ValueError(
            f"evidence {e.id} unit {res.unit!r} does not match requirement {req.id} unit {req.unit!r}"
        )

    if e.producer_kind is ProducerKind.WAIVER:
        return Verdict.PASS, ()

    # Fail closed: ML is only trusted inside its applicability domain; unknown (None) counts as outside.
    if e.producer_kind is ProducerKind.ML_PREDICTION and res.in_domain is not True:
        return Verdict.INCONCLUSIVE, (
            Reason(
                code=ReasonCode.OUT_OF_DOMAIN,
                message=f"ML evidence {e.id} is outside (or has no) applicability domain",
                evidence_ids=(e.id,),
                detail=dict(res.domain_report) if res.domain_report is not None else {},
            ),
        )

    bounds = verdict_interval(e)
    if bounds is None:
        if res.point is not None:
            return Verdict.INCONCLUSIVE, (
                Reason(
                    code=ReasonCode.MARGIN_BELOW_UNCERTAINTY,
                    message=f"evidence {e.id} has a point value but no bounded uncertainty interval",
                    evidence_ids=(e.id,),
                ),
            )
        return Verdict.INCONCLUSIVE, (
            Reason(
                code=ReasonCode.NO_EVIDENCE,
                message=f"evidence {e.id} has neither an interval nor a point value",
                evidence_ids=(e.id,),
            ),
        )

    lo, hi = bounds
    limit = req.limit
    if req.op is Comparator.LE:
        passes, fails = hi <= limit, lo > limit
    else:
        passes, fails = lo >= limit, hi < limit
    if passes:
        return Verdict.PASS, ()
    if fails:
        return Verdict.FAIL, ()
    return Verdict.INCONCLUSIVE, (
        Reason(
            code=ReasonCode.MARGIN_BELOW_UNCERTAINTY,
            message=f"interval [{lo}, {hi}] of {e.id} straddles the limit {req.op.value} {limit} {req.unit}",
            evidence_ids=(e.id,),
        ),
    )
