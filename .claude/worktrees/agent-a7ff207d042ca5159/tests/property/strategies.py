"""Hypothesis strategies for small random projects, built directly as domain objects (no files).

A project case has at most 6 claims and 12 evidence items over two subjects and two quantities, a fixed
producer catalogue (shared predictors included, so independence matters) and policies from DEFAULT_POLICIES.
Interval endpoints are half-integers around the limits so that PASS, FAIL and straddling verdicts all occur.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from hypothesis import strategies as st

from reval.core.canonical import canonical_json, content_id, difference_unit, sha256_hex
from reval.core.diff import diff_snapshots
from reval.core.freshness import carry_forward, classify_all
from reval.core.selectors import selector_hash
from reval.core.status import AssessInput, assess_all
from reval.domain import (
    DEFAULT_POLICIES,
    Artifact,
    ArtifactKind,
    ArtifactVersion,
    Assessment,
    Assumption,
    Claim,
    Comparator,
    Criticality,
    Dependency,
    Evidence,
    EvidenceResult,
    FreshnessClass,
    Interval,
    Producer,
    ProducerKind,
    Provenance,
    Requirement,
    RowGroupInfo,
    Scope,
    Snapshot,
    Tolerance,
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


# -- freshness-aware cases (I3, I7) ------------------------------------------------------------------


@dataclass(frozen=True)
class ImpactCase:
    """Evidence recorded at ``old`` and a ``new`` snapshot after a random change."""

    old: Snapshot
    new: Snapshot
    evidence: tuple[Evidence, ...]


_DEP_CHOICES = ("params#/f0", "params#/f1", "params", "data[temp]", "data[x]", "data", "params#/f0+data[x]")
_COLS = ("temp", "x")
Groups = dict[str, tuple[float, float, int]]


def _params_version(f0: float, f1: float) -> ArtifactVersion:
    values = {"/f0": f0, "/f1": f1}
    return ArtifactVersion(
        artifact_id="params",
        content_hash=sha256_hex(canonical_json(values)),
        field_hashes={k: sha256_hex(canonical_json(v)) for k, v in values.items()},
        field_values=values,
    )


def _data_version(groups: Groups) -> ArtifactVersion:
    """Groups map name -> (x_lo, x_hi, temp_tag); changing the tag modifies only the ``temp`` column."""
    hashes: dict[str, str] = {}
    row_groups: dict[str, RowGroupInfo] = {}
    for g, (lo, hi, tag) in sorted(groups.items()):
        hashes[f"g={g}/c=x"] = sha256_hex(canonical_json([g, lo, hi]))
        hashes[f"g={g}/c=temp"] = sha256_hex(canonical_json([g, tag]))
        row_groups[g] = RowGroupInfo(n_rows=10, bbox={"x": (lo, hi)})
    for c in _COLS:
        per_group = sorted((k, h) for k, h in hashes.items() if k.endswith(f"/c={c}"))
        hashes[f"c={c}"] = sha256_hex(canonical_json(per_group))
    return ArtifactVersion(
        artifact_id="data",
        content_hash=sha256_hex(canonical_json(sorted(hashes.items()))),
        field_hashes=hashes,
        row_groups=row_groups,
    )


def _world(base: Snapshot, f0: float, f1: float, groups: Groups) -> Snapshot:
    fields = {k: getattr(base, k) for k in type(base).model_fields if k != "id"}
    fields.update(
        artifacts={
            "params": Artifact(id="params", kind=ArtifactKind.PARAMS, path="p.yaml", hasher="yaml-fields"),
            "data": Artifact(
                id="data", kind=ArtifactKind.DATASET, path="d.csv", hasher="dataframe", key=("group",)
            ),
        },
        versions={"params": _params_version(f0, f1), "data": _data_version(groups)},
        assumptions={"A": Assumption(id="A", statement="s", variable="f0", unit="1", bounds=(0.0, 2.0))},
    )
    return Snapshot.create(**fields)


def _dep_hashes(world: Snapshot, spec: str) -> tuple[Dependency, ...]:
    return tuple(
        Dependency(selector=s, version_hash=selector_hash(world, s)) for s in sorted(spec.split("+"))
    )


def _fields(e: Evidence, *skip: str) -> dict[str, object]:
    return {k: getattr(e, k) for k in type(e).model_fields if k != "id" and k not in skip}


@st.composite
def impact_cases(draw: st.DrawFn, *, change: bool = True) -> ImpactCase:
    """Random evidence (deps, tolerances, scope boxes) recorded at ``old`` and a random change to ``new``."""
    case = draw(cases())
    f0 = draw(st.sampled_from([0.6, 0.8, 1.0, 1.2, 1.4]))
    f1 = draw(st.sampled_from([0.6, 1.0, 1.4]))
    groups: Groups = {
        "g1": (0.0, 1.0, 0),
        "g2": (draw(st.sampled_from([0.0, 2.0, 5.0])), draw(st.sampled_from([6.0, 8.0])), 0),
    }
    old = _world(case.snapshot, f0, f1, groups)
    new = old
    if change:
        n_f0 = draw(st.sampled_from([f0, f0, f0 + 0.05, f0 + 0.3, 3.0]))
        n_f1 = draw(st.sampled_from([f1, f1, f1 + 0.05]))
        new_groups = dict(groups)
        what = draw(st.sampled_from(["none", "add", "remove", "modify"]))
        if what == "add":
            lo = draw(st.sampled_from([0.0, 3.0, 20.0]))
            new_groups["g3"] = (lo, lo + draw(st.sampled_from([1.0, 4.0])), 0)
        elif what == "remove":
            del new_groups["g2"]
        elif what == "modify":
            glo, ghi, _ = new_groups["g2"]
            new_groups["g2"] = (glo, ghi, 1)
        new = _world(case.snapshot, n_f0, n_f1, new_groups)
    evidence: list[Evidence] = []
    for inp in case.items:
        e = inp.evidence
        spec = draw(st.sampled_from(_DEP_CHOICES))
        tolerances: tuple[Tolerance, ...] = ()
        if draw(st.booleans()):
            tolerances = (
                Tolerance(
                    selector=draw(st.sampled_from(["params#/f0", "params#/f1"])),
                    sensitivity=draw(st.sampled_from([0.0, 1.0, 10.0, 40.0])),
                    input_unit="1",
                    output_unit=difference_unit(e.result.unit),
                    valid_range=(0.5, 1.5),
                    safety_factor=draw(st.sampled_from([1.0, 1.5])),
                    source="prop",
                    assumption_id="A",
                ),
            )
        lo = draw(st.sampled_from([0.0, 2.0, 4.0]))
        box = draw(st.sampled_from([{}, {"x": (lo, lo + 1.0)}, {"x": (100.0, 200.0)}, {"other": (0.0, 1.0)}]))
        waiver = e.waiver
        if waiver is not None:
            # A waiver is exactly fresh only while it pins the current requirement; keep the generator honest.
            req = case.snapshot.requirements[case.snapshot.claims[waiver.claim_id].requirement_id]
            waiver = waiver.model_copy(update={"requirement_hash": content_id(req)})
        evidence.append(
            Evidence.create(
                **_fields(e, "deps", "scope", "tolerances", "provenance", "waiver"),
                waiver=waiver,  # type: ignore[arg-type]
                deps=_dep_hashes(old, spec),
                scope=Scope(box=box, assumption_ids=()),
                tolerances=tolerances,
                provenance=e.provenance.model_copy(update={"snapshot_id": old.id}),
            )
        )
    return ImpactCase(old=old, new=new, evidence=tuple({e.id: e for e in evidence}.values()))


def strip_declarations(e: Evidence) -> Evidence:
    """``e`` with every tolerance and scope box replaced by "undeclared" (I3)."""
    return Evidence.create(
        **_fields(e, "tolerances", "scope"),  # type: ignore[arg-type]
        tolerances=(),
        scope=Scope(box={}, assumption_ids=e.scope.assumption_ids),
    )


def classify_and_assess(old: Snapshot, new: Snapshot, evidence: Sequence[Evidence]) -> dict[str, Assessment]:
    """The Project.assess pipeline on in-memory objects: diff, classify, carry forward, assess."""
    changes = diff_snapshots(old, new)
    freshness = classify_all(evidence, {old.id: old}, new, {old.id: changes})
    items: list[AssessInput] = []
    for e in evidence:
        fr = freshness[e.id]
        if fr.cls is FreshnessClass.CARRY_FORWARD:
            items.append(AssessInput(carry_forward(e, fr, new), FreshnessClass.CARRY_FORWARD, original=e))
        else:
            items.append(AssessInput(e, fr.cls))
    return assess_all(new, items, changes)
