"""Freshness invariants (docs/03 §5). I5: a larger |Δf| never yields a narrower carried-forward interval."""

from hypothesis import given
from hypothesis import strategies as st

from reval.core.canonical import canonical_json, sha256_hex
from reval.core.diff import diff_snapshots
from reval.core.freshness import carry_forward, classify_evidence
from reval.core.selectors import selector_hash
from reval.domain import (
    DEFAULT_POLICIES,
    Artifact,
    ArtifactKind,
    ArtifactVersion,
    Assumption,
    Dependency,
    Evidence,
    EvidenceResult,
    FreshnessClass,
    Interval,
    Producer,
    ProducerKind,
    Provenance,
    Snapshot,
    Tolerance,
)

F = FreshnessClass
SEL = "params#/f"
PRODUCER = Producer(
    id="p",
    kind=ProducerKind.PHYSICS_SIM,
    quantities=("q",),
    fidelity=2,
    cost=1.0,
    code_hash="c",
    depends_on=(SEL,),
)


def _snapshot(f: float) -> Snapshot:
    version = ArtifactVersion(
        artifact_id="params",
        content_hash=sha256_hex(canonical_json({"f": f})),
        field_hashes={"/f": sha256_hex(canonical_json(f))},
        field_values={"/f": f},
    )
    return Snapshot.create(
        manifest_hash="m",
        quantities={"q": "degC"},
        artifacts={
            "params": Artifact(id="params", kind=ArtifactKind.PARAMS, path="p.yaml", hasher="yaml-fields")
        },
        versions={"params": version},
        assumptions={"A": Assumption(id="A", statement="s", variable="f", unit="1", bounds=(0.0, 2.0))},
        requirements={},
        subjects={},
        claims={},
        policies=dict(DEFAULT_POLICIES),
        producers={"p": PRODUCER},
    )


def _evidence(s: Snapshot, sens: float, kappa: float, lo: float, hi: float) -> Evidence:
    return Evidence.create(
        producer_id="p",
        producer_kind=ProducerKind.PHYSICS_SIM,
        fidelity=2,
        subject_id="S",
        result=EvidenceResult(
            quantity="q", unit="degC", point=(lo + hi) / 2, interval=Interval(lo=lo, hi=hi, unit="degC")
        ),
        deps=(Dependency(selector=SEL, version_hash=selector_hash(s, SEL)),),
        tolerances=(
            Tolerance(
                selector=SEL,
                sensitivity=sens,
                input_unit="1",
                output_unit="K",
                valid_range=(0.5, 1.5),
                safety_factor=kappa,
                source="test",
                assumption_id="A",
            ),
        ),
        provenance=Provenance(producer_code_hash="c", snapshot_id=s.id),
        cost=1.0,
    )


def _width(e: Evidence, old: Snapshot, f_new: float) -> float | None:
    """Width of the carried interval at f_new, the original width if fresh, None if invalidated."""
    new = _snapshot(f_new)
    fr = classify_evidence(e, old, new, diff_snapshots(old, new))
    assert e.result.interval is not None
    if fr.cls is F.INVALIDATED:
        return None
    if fr.cls is F.CARRY_FORWARD:
        carried = carry_forward(e, fr, new).result.interval
        assert carried is not None
        return carried.width
    return e.result.interval.width


@given(
    f0=st.floats(0.4, 1.6, allow_nan=False),
    d_small=st.floats(0.0, 1.0, allow_nan=False),
    extra=st.floats(0.0, 1.0, allow_nan=False),
    sign=st.sampled_from([-1.0, 1.0]),
    sens=st.floats(0.0, 100.0, allow_nan=False),
    kappa=st.floats(1.0, 3.0, allow_nan=False),
    lo=st.floats(-50.0, 150.0, allow_nan=False),
    w=st.floats(0.0, 20.0, allow_nan=False),
)
def test_i5_monotone_inflation(
    f0: float, d_small: float, extra: float, sign: float, sens: float, kappa: float, lo: float, w: float
) -> None:
    old = _snapshot(f0)
    e = _evidence(old, sens, kappa, lo, lo + w)
    small = _width(e, old, f0 + sign * d_small)
    large = _width(e, old, f0 + sign * (d_small + extra))
    if large is not None:
        # valid_range is an interval: if the larger step stays inside, so does the smaller one.
        assert small is not None
        assert large >= small - 1e-9
        assert large >= w - 1e-9  # never narrower than the recorded interval
