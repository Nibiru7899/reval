"""P4-04: ML applicability gate in verdicts and claim status (docs/03 sections 2-3, docs/10 4.4-4.5)."""

from hypothesis import given
from hypothesis import strategies as st

from reval.core.status import AssessInput, assess_claim
from reval.core.verdicts import verdict
from reval.domain import (
    Claim,
    Comparator,
    Criticality,
    Evidence,
    EvidenceResult,
    FreshnessClass,
    Interval,
    Producer,
    ProducerKind,
    Provenance,
    ReasonCode,
    Requirement,
    Snapshot,
    Status,
    Verdict,
)
from reval.domain.policies import DEFAULT_POLICIES

K = ProducerKind
L = 100.0
finite = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False)


def _req(op: Comparator) -> Requirement:
    return Requirement(
        id="R", text="t", quantity="q", op=op, limit=L, unit="degC", criticality=Criticality.MEDIUM
    )


def _ml(lo: float | None, hi: float | None, in_domain: bool | None) -> Evidence:
    return _ev("ml", K.ML_PREDICTION, lo, hi, in_domain)


def _ev(pid: str, kind: ProducerKind, lo: float | None, hi: float | None, in_domain: bool | None) -> Evidence:
    interval = Interval(lo=lo, hi=hi, unit="degC") if lo is not None and hi is not None else None
    return Evidence.create(
        producer_id=pid,
        producer_kind=kind,
        fidelity=1 if kind is K.ML_PREDICTION else 2,
        subject_id="S",
        result=EvidenceResult(
            quantity="q",
            unit="degC",
            point=None if lo is None or hi is None else (lo + hi) / 2,
            interval=interval,
            uncertainty_kind="conformal" if interval else "none",
            in_domain=in_domain,
            domain_report={"inside": bool(in_domain)},
        ),
        deps=(),
        provenance=Provenance(producer_code_hash=f"c-{pid}", snapshot_id="s"),
        cost=1.0,
    )


@given(lo=finite, width=st.floats(min_value=0, max_value=500), op=st.sampled_from(list(Comparator)))
def test_out_of_domain_ml_is_always_inconclusive(lo: float, width: float, op: Comparator) -> None:
    for dom in (False, None):
        v, reasons = verdict(_ml(lo, lo + width, dom), _req(op))
        assert v is Verdict.INCONCLUSIVE
        assert [r.code for r in reasons] == [ReasonCode.OUT_OF_DOMAIN]


@given(lo=finite, width=st.floats(min_value=0, max_value=500))
def test_ge_le_symmetry_for_in_domain_ml(lo: float, width: float) -> None:
    hi = lo + width
    v_le, _ = verdict(_ml(lo, hi, True), _req(Comparator.LE))
    # Reflecting the interval about the limit swaps the comparator and keeps the verdict.
    v_ge, _ = verdict(_ml(2 * L - hi, 2 * L - lo, True), _req(Comparator.GE))
    assert v_le is v_ge


def test_boundary_inclusivity() -> None:
    le, ge = _req(Comparator.LE), _req(Comparator.GE)
    assert verdict(_ml(90.0, L, True), le)[0] is Verdict.PASS  # hi == L
    assert verdict(_ml(L, 110.0, True), le)[0] is Verdict.INCONCLUSIVE  # lo == L < hi: not FAIL
    assert verdict(_ml(L, 110.0, True), ge)[0] is Verdict.PASS  # lo == L
    assert verdict(_ml(90.0, L, True), ge)[0] is Verdict.INCONCLUSIVE  # hi == L > lo: not FAIL


def test_unbounded_conformal_is_inconclusive_not_fail() -> None:
    e = Evidence.create(
        producer_id="ml",
        producer_kind=K.ML_PREDICTION,
        fidelity=1,
        subject_id="S",
        result=EvidenceResult(
            quantity="q", unit="degC", point=500.0, uncertainty_kind="none", in_domain=True
        ),
        deps=(),
        provenance=Provenance(producer_code_hash="c", snapshot_id="s"),
        cost=1.0,
    )
    v, reasons = verdict(e, _req(Comparator.LE))
    assert v is Verdict.INCONCLUSIVE
    assert reasons[0].code is ReasonCode.MARGIN_BELOW_UNCERTAINTY


def _snapshot() -> Snapshot:
    def prod(pid: str, kind: ProducerKind, fid: int, pred: str) -> Producer:
        return Producer(
            id=pid,
            kind=kind,
            quantities=("q",),
            fidelity=fid,
            cost=1.0,
            code_hash=f"c-{pid}",
            depends_on=(pred,),
            predictors=(pred,),
        )

    return Snapshot.create(
        manifest_hash="m",
        quantities={"q": "degC"},
        artifacts={},
        versions={},
        assumptions={},
        requirements={"R": _req(Comparator.LE)},
        subjects={},
        claims={"C": Claim(id="C", requirement_id="R", subject_id="S", policy_id="medium")},
        policies=DEFAULT_POLICIES,
        producers={
            "ml": prod("ml", K.ML_PREDICTION, 1, "tpm"),
            "sim": prod("sim", K.PHYSICS_SIM, 2, "lptn"),
        },
    )


@given(lo=st.floats(min_value=0, max_value=90), width=st.floats(min_value=0, max_value=9))
def test_out_of_domain_ml_never_completes_a_medium_clause(lo: float, width: float) -> None:
    snap = _snapshot()
    fx = FreshnessClass.FRESH_EXACT
    items = [
        AssessInput(evidence=_ml(lo, lo + width, False), freshness=fx),  # would PASS if in domain
        AssessInput(evidence=_ev("sim", K.PHYSICS_SIM, lo, lo + width, None), freshness=fx),
    ]
    a = assess_claim(snap.claims["C"], snap, items)
    assert a.status is not Status.SUPPORTED
    # The same evidence in domain does support the claim, so the gate is what blocks it.
    items[0] = AssessInput(evidence=_ml(lo, lo + width, True), freshness=fx)
    assert assess_claim(snap.claims["C"], snap, items).status is Status.SUPPORTED
