"""Hypothesis strategies for small random projects, built directly as domain objects (no files).

A project case has at most 6 claims and 12 evidence items over two subjects and two quantities, a fixed
producer catalogue (shared predictors included, so independence matters) and policies from DEFAULT_POLICIES.
Interval endpoints are half-integers around the limits so that PASS, FAIL and straddling verdicts all occur.
"""

from dataclasses import dataclass

from hypothesis import strategies as st

from reval.core.status import AssessInput
from reval.domain import (
    DEFAULT_POLICIES,
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
    Requirement,
    Snapshot,
    Waiver,
)

K = ProducerKind
FX = FreshnessClass.FRESH_EXACT
OOS = FreshnessClass.FRESH_OUT_OF_SCOPE
INV = FreshnessClass.INVALIDATED

SUBJECTS = ("S1", "S2")
UNIT = {"q": "degC", "q2": "A"}


def _producer(pid: str, kind: ProducerKind, fidelity: int, predictors: tuple[str, ...] = ()) -> Producer:
    return Producer(
        id=pid,
        kind=kind,
        quantities=("q", "q2", "q9"),
        fidelity=fidelity,
        cost=0.0 if kind is K.WAIVER else 1.0,
        code_hash=f"code-{pid}",
        depends_on=(*predictors, "inputs"),
        predictors=predictors,
    )


PRODUCERS: dict[str, Producer] = {
    p.id: p
    for p in [
        _producer("ml", K.ML_PREDICTION, 1, ("tpm",)),
        _producer("ml_lptn", K.ML_PREDICTION, 1, ("lptn",)),  # shares a predictor with `sim`
        _producer("sim", K.PHYSICS_SIM, 2, ("lptn",)),
        _producer("sim_lo", K.PHYSICS_SIM, 1, ("lptn2",)),
        _producer("meas", K.MEASUREMENT, 3),
        _producer("ana", K.ANALYTIC, 3),
        _producer("ana_lo", K.ANALYTIC, 2),
        _producer("waive", K.WAIVER, 0),
    ]
}

_LIMITS = {"q": (Comparator.LE, 100.0), "q2": (Comparator.GE, 10.0)}


@dataclass(frozen=True)
class Case:
    """A random project: the snapshot plus the evidence items with their freshness classes."""

    snapshot: Snapshot
    items: tuple[AssessInput, ...]


def make_evidence(
    pid: str,
    subject: str,
    quantity: str,
    lo: float,
    hi: float,
    *,
    in_domain: bool | None,
    fidelity: int,
    seed: int | None,
    waiver_claim: str = "C0",
    derived_from: str | None = None,
) -> Evidence:
    """Build one Evidence item of the catalogue producer ``pid``."""
    prod = PRODUCERS[pid]
    unit = "degC" if quantity in ("q", "q9") else "A"
    return Evidence.create(
        producer_id=pid,
        producer_kind=prod.kind,
        fidelity=fidelity,
        subject_id=subject,
        result=EvidenceResult(
            quantity=quantity,
            unit=unit,
            point=(lo + hi) / 2,
            interval=Interval(lo=lo, hi=hi, unit=unit),
            uncertainty_kind="model_form",
            in_domain=in_domain,
        ),
        deps=(),
        provenance=Provenance(producer_code_hash=prod.code_hash, snapshot_id="s0", seed=seed),
        cost=prod.cost,
        derived_from_evidence=derived_from,
        waiver=(
            Waiver(author="a", justification="reviewed", claim_id=waiver_claim, requirement_hash="h")
            if prod.kind is K.WAIVER
            else None
        ),
    )


def _interval_for(quantity: str, a: int, w: int) -> tuple[float, float]:
    base = a / 2.0 if quantity == "q" else a / 10.0
    width = w / 2.0 if quantity == "q" else w / 10.0
    return base, base + width


@st.composite
def evidence_items(
    draw: st.DrawFn, claim_ids: tuple[str, ...], subjects: tuple[str, ...] = SUBJECTS
) -> Evidence:
    pid = draw(st.sampled_from(sorted(PRODUCERS)))
    quantity = draw(st.sampled_from(["q", "q2"]))
    a = draw(st.integers(120, 260) if quantity == "q" else st.integers(40, 160))
    w = draw(st.sampled_from([0, 0, 2, 10, 40, 80]))
    lo, hi = _interval_for(quantity, a, w)
    return make_evidence(
        pid,
        draw(st.sampled_from(subjects)),
        quantity,
        lo,
        hi,
        in_domain=draw(st.sampled_from([True, True, False, None])),
        fidelity=draw(st.sampled_from([PRODUCERS[pid].fidelity, PRODUCERS[pid].fidelity, 0, 3])),
        seed=draw(st.sampled_from([None, 1, 2])),
        waiver_claim=draw(st.sampled_from(claim_ids)),
    )


def build_snapshot(reqs: dict[str, Requirement], claims: dict[str, Claim]) -> Snapshot:
    return Snapshot.create(
        manifest_hash="m",
        quantities={"q": "degC", "q2": "A", "q9": "degC"},
        artifacts={},
        versions={},
        assumptions={},
        requirements=reqs,
        subjects={},
        claims=claims,
        policies=dict(DEFAULT_POLICIES),
        producers=PRODUCERS,
    )


def single_claim_snapshot() -> Snapshot:
    """One low-criticality claim C0 on S1 for quantity q (limit 100 degC)."""
    req = Requirement(
        id="R",
        text="t",
        quantity="q",
        op=Comparator.LE,
        limit=100.0,
        unit="degC",
        criticality=Criticality.LOW,
    )
    return build_snapshot({"R": req}, {"C0": Claim(id="C0", requirement_id="R", subject_id="S1")})


@st.composite
def cases(draw: st.DrawFn) -> Case:
    crit = {
        "R": draw(st.sampled_from(list(Criticality))),
        "R-GE": draw(st.sampled_from(list(Criticality))),
    }
    reqs = {
        rid: Requirement(
            id=rid,
            text="t",
            quantity=q,
            op=_LIMITS[q][0],
            limit=_LIMITS[q][1],
            unit=UNIT[q],
            criticality=crit[rid],
        )
        for rid, q in (("R", "q"), ("R-GE", "q2"))
    }
    n_claims = draw(st.integers(1, 6))
    claims = {
        f"C{i}": Claim(
            id=f"C{i}",
            requirement_id=draw(st.sampled_from(["R", "R-GE"])),
            subject_id=draw(st.sampled_from(SUBJECTS)),
            policy_id=draw(st.sampled_from([None, "low", "medium", "high"])),
        )
        for i in range(n_claims)
    }
    evidence = draw(st.lists(evidence_items(tuple(claims)), max_size=12))
    freshness = draw(
        st.lists(st.sampled_from([FX, FX, OOS, INV]), min_size=len(evidence), max_size=len(evidence))
    )
    by_id: dict[str, AssessInput] = {}
    for e, f in zip(evidence, freshness, strict=True):
        by_id.setdefault(e.id, AssessInput(evidence=e, freshness=f))
    snapshot = build_snapshot(reqs, claims)
    return Case(snapshot=snapshot, items=tuple(by_id[k] for k in sorted(by_id)))


def irrelevant_items(claim_ids: tuple[str, ...]) -> st.SearchStrategy[list[Evidence]]:
    """Items no claim can use: an unknown subject ``S9`` (any quantity) or the unused quantity ``q9``."""

    @st.composite
    def one(draw: st.DrawFn) -> Evidence:
        pid = draw(st.sampled_from(sorted(PRODUCERS)))
        other_subject = draw(st.booleans())
        quantity = "q" if other_subject else "q9"
        subject = "S9" if other_subject else draw(st.sampled_from(SUBJECTS))
        lo = draw(st.integers(0, 300)) / 2.0
        hi = lo + draw(st.sampled_from([0, 1, 20]))
        return make_evidence(
            pid,
            subject,
            quantity,
            lo,
            hi,
            in_domain=draw(st.sampled_from([True, False, None])),
            fidelity=PRODUCERS[pid].fidelity,
            seed=draw(st.sampled_from([None, 1, 2])),
            waiver_claim=draw(st.sampled_from(claim_ids)),
        )

    return st.lists(one(), max_size=6)
