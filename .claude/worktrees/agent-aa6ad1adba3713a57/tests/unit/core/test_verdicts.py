"""P2-08: evidence verdicts (docs/03 §2, docs/10 §4.4)."""

from typing import Any

import pytest

from reval.core.verdicts import verdict
from reval.domain import (
    Comparator,
    Criticality,
    Evidence,
    EvidenceResult,
    Interval,
    ProducerKind,
    Provenance,
    ReasonCode,
    Requirement,
    Verdict,
    Waiver,
)

K = ProducerKind
P, F, INC = Verdict.PASS, Verdict.FAIL, Verdict.INCONCLUSIVE
MARGIN = ReasonCode.MARGIN_BELOW_UNCERTAINTY


def _req(op: Comparator = Comparator.LE, limit: float = 100.0) -> Requirement:
    return Requirement(
        id="R",
        text="t",
        quantity="q",
        op=op,
        limit=limit,
        unit="degC",
        criticality=Criticality.LOW,
    )


def _ev(
    kind: ProducerKind,
    lo: float | None = None,
    hi: float | None = None,
    *,
    point: float | None = None,
    ukind: Any = "none",
    in_domain: bool | None = None,
    unit: str = "degC",
    quantity: str = "q",
    domain_report: dict[str, Any] | None = None,
) -> Evidence:
    interval = Interval(lo=lo, hi=hi, unit=unit) if lo is not None and hi is not None else None
    return Evidence.create(
        producer_id="p",
        producer_kind=kind,
        fidelity=1,
        subject_id="S",
        result=EvidenceResult(
            quantity=quantity,
            unit=unit,
            point=point,
            interval=interval,
            uncertainty_kind=ukind,
            in_domain=in_domain,
            domain_report=domain_report,
        ),
        deps=(),
        provenance=Provenance(producer_code_hash="c", snapshot_id="s"),
        cost=1.0,
        waiver=(
            Waiver(author="a", justification="j", claim_id="C", requirement_hash="h")
            if kind is K.WAIVER
            else None
        ),
    )


LE, GE = Comparator.LE, Comparator.GE

# (kind, op, lo, hi, in_domain, expected verdict, expected reason codes); limit = 100.
INTERVAL_ROWS = [
    # measurement
    (K.MEASUREMENT, LE, 90, 95, None, P, ()),
    (K.MEASUREMENT, LE, 101, 105, None, F, ()),
    (K.MEASUREMENT, LE, 95, 105, None, INC, (MARGIN,)),
    (K.MEASUREMENT, GE, 101, 105, None, P, ()),
    (K.MEASUREMENT, GE, 90, 95, None, F, ()),
    (K.MEASUREMENT, GE, 95, 105, None, INC, (MARGIN,)),
    # physics sim
    (K.PHYSICS_SIM, LE, 90, 100, None, P, ()),
    (K.PHYSICS_SIM, LE, 100.5, 110, None, F, ()),
    (K.PHYSICS_SIM, LE, 99, 101, None, INC, (MARGIN,)),
    (K.PHYSICS_SIM, GE, 100, 110, None, P, ()),
    (K.PHYSICS_SIM, GE, 80, 99.5, None, F, ()),
    (K.PHYSICS_SIM, GE, 99, 101, None, INC, (MARGIN,)),
    # analytic with an interval (declared bound)
    (K.ANALYTIC, LE, 50, 60, None, P, ()),
    (K.ANALYTIC, LE, 150, 160, None, F, ()),
    (K.ANALYTIC, GE, 150, 160, None, P, ()),
    (K.ANALYTIC, GE, 50, 60, None, F, ()),
    # ML in domain
    (K.ML_PREDICTION, LE, 90, 95, True, P, ()),
    (K.ML_PREDICTION, LE, 101, 105, True, F, ()),
    (K.ML_PREDICTION, LE, 95, 105, True, INC, (MARGIN,)),
    (K.ML_PREDICTION, GE, 101, 105, True, P, ()),
    (K.ML_PREDICTION, GE, 90, 95, True, F, ()),
    (K.ML_PREDICTION, GE, 95, 105, True, INC, (MARGIN,)),
    # ML out of domain / unknown domain: always inconclusive, even when the interval would decide
    (K.ML_PREDICTION, LE, 90, 95, False, INC, (ReasonCode.OUT_OF_DOMAIN,)),
    (K.ML_PREDICTION, LE, 101, 105, False, INC, (ReasonCode.OUT_OF_DOMAIN,)),
    (K.ML_PREDICTION, GE, 101, 105, None, INC, (ReasonCode.OUT_OF_DOMAIN,)),
    (K.ML_PREDICTION, GE, 90, 95, None, INC, (ReasonCode.OUT_OF_DOMAIN,)),
    # boundaries (inclusive on the pass side)
    (K.MEASUREMENT, LE, 90, 100, None, P, ()),  # hi == L passes
    (K.MEASUREMENT, LE, 100, 105, None, INC, (MARGIN,)),  # lo == L < hi
    (K.MEASUREMENT, LE, 100, 100, None, P, ()),  # degenerate at L
    (K.MEASUREMENT, GE, 100, 105, None, P, ()),  # lo == L passes
    (K.MEASUREMENT, GE, 95, 100, None, INC, (MARGIN,)),  # lo < hi == L
    (K.MEASUREMENT, GE, 100, 100, None, P, ()),
]


@pytest.mark.parametrize(("kind", "op", "lo", "hi", "in_domain", "expected", "codes"), INTERVAL_ROWS)
def test_interval_verdict_table(
    kind: ProducerKind,
    op: Comparator,
    lo: float,
    hi: float,
    in_domain: bool | None,
    expected: Verdict,
    codes: tuple[ReasonCode, ...],
) -> None:
    e = _ev(kind, lo, hi, in_domain=in_domain)
    v, reasons = verdict(e, _req(op))
    assert v is expected
    assert tuple(r.code for r in reasons) == codes
    assert all(r.evidence_ids == (e.id,) for r in reasons)


@pytest.mark.parametrize(
    ("op", "point", "expected"),
    [(LE, 99.0, P), (LE, 100.0, P), (LE, 100.01, F), (GE, 100.0, P), (GE, 101.0, P), (GE, 99.99, F)],
)
def test_exact_point_is_a_degenerate_interval(op: Comparator, point: float, expected: Verdict) -> None:
    v, reasons = verdict(_ev(K.ANALYTIC, point=point, ukind="exact"), _req(op))
    assert v is expected
    assert reasons == ()


def test_interval_takes_precedence_over_exact_point() -> None:
    e = _ev(K.ANALYTIC, 95, 105, point=90.0, ukind="exact")
    assert verdict(e, _req())[0] is INC


@pytest.mark.parametrize("kind", [K.MEASUREMENT, K.PHYSICS_SIM, K.ANALYTIC])
def test_point_without_interval_is_margin_below_uncertainty(kind: ProducerKind) -> None:
    v, reasons = verdict(_ev(kind, point=10.0, ukind="conformal"), _req())
    assert v is INC
    assert [r.code for r in reasons] == [MARGIN]


def test_ml_unbounded_quantile_in_domain_is_margin_below_uncertainty() -> None:
    v, reasons = verdict(_ev(K.ML_PREDICTION, point=10.0, ukind="conformal", in_domain=True), _req())
    assert v is INC
    assert [r.code for r in reasons] == [MARGIN]


def test_neither_interval_nor_point_is_no_evidence() -> None:
    v, reasons = verdict(_ev(K.MEASUREMENT), _req())
    assert v is INC
    assert [r.code for r in reasons] == [ReasonCode.NO_EVIDENCE]


def test_out_of_domain_detail_is_domain_report() -> None:
    report = {"inside": False, "score": 3.5}
    _, reasons = verdict(_ev(K.ML_PREDICTION, 1, 2, in_domain=False, domain_report=report), _req())
    assert reasons[0].detail == report


@pytest.mark.parametrize("op", [LE, GE])
def test_waiver_always_passes(op: Comparator) -> None:
    assert verdict(_ev(K.WAIVER, 500, 600), _req(op)) == (P, ())
    assert verdict(_ev(K.WAIVER), _req(op)) == (P, ())


def test_unit_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="unit"):
        verdict(_ev(K.MEASUREMENT, 1, 2, unit="K"), _req())


def test_interval_unit_mismatch_raises() -> None:
    e = _ev(K.MEASUREMENT, 1, 2).model_copy(
        update={"result": EvidenceResult(quantity="q", unit="degC", interval=Interval(lo=1, hi=2, unit="K"))}
    )
    with pytest.raises(ValueError, match="unit"):
        verdict(e, _req())


def test_quantity_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="quantity"):
        verdict(_ev(K.MEASUREMENT, 1, 2, quantity="other"), _req())
