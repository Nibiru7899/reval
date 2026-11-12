"""run_producer: deterministic ids, dependency hashes, assumes merge (D9), quantity validation."""

from typing import Any

import pytest

from reval.core.selectors import selector_hash
from reval.domain.engineering import Subject
from reval.domain.evidence import Scope
from reval.errors import ProducerError
from reval.sdk import DEFAULT_REGISTRY, ProducerKind, ProducerOutput, interval_result, producer
from reval.sdk.runner import run_producer

P = "mini.producers:"


def test_ids_identical_across_runs_and_deps_use_snapshot_hashes(mini: Any) -> None:
    snap = mini.snapshot()
    s1 = snap.subjects["S1"]
    a = run_producer(mini.registry, P + "sim_temp", s1, snap, mini.root)
    b = run_producer(mini.registry, P + "sim_temp", s1, snap, mini.root)
    assert [e.id for e in a] == [e.id for e in b] and len(a) == 1
    e = a[0]
    assert {d.selector for d in e.deps} == {"params#/load/scale", "params#/sim/gain"}
    for d in e.deps:
        assert d.version_hash == selector_hash(snap, d.selector)
    assert e.result.interval is not None and (e.result.interval.lo, e.result.interval.hi) == (58.0, 62.0)
    assert e.provenance.snapshot_id == snap.id and e.provenance.seed is not None


def test_assumes_always_in_scope(mini: Any) -> None:
    snap = mini.snapshot()
    s1 = snap.subjects["S1"]

    @producer(
        kind=ProducerKind.ANALYTIC,
        quantity="temp_peak",
        cost=1.0,
        depends_on=["params#/load/scale"],
        assumes=["A-ambient"],
        id="t:omits_scope",
        registry=mini.registry,
    )
    def omits(subject: Subject, ctx: Any) -> ProducerOutput:
        return ProducerOutput(
            results=(interval_result("temp_peak", "degC", 1.0, 0.0, 2.0, uncertainty_kind="sensor"),),
            scope=Scope(),
        )

    mini.registry.load_modules([], mini.root)
    snap = mini.snapshot()
    (e,) = run_producer(mini.registry, "t:omits_scope", s1, snap, mini.root)
    assert e.scope.assumption_ids == ("A-ambient",)
    (p,) = run_producer(mini.registry, P + "predict_temp", s1, snap, mini.root)
    assert p.scope.assumption_ids == ("A-ambient",)


def test_wrong_quantity_and_unit_raise(mini: Any) -> None:
    @producer(kind=ProducerKind.ANALYTIC, quantity="temp_peak", cost=1.0, id="t:badq", registry=mini.registry)
    def badq(subject: Subject, ctx: Any) -> ProducerOutput:
        return ProducerOutput(
            results=(interval_result("shaft_d", "mm", 1.0, 1.0, 1.0, uncertainty_kind="exact"),)
        )

    @producer(kind=ProducerKind.ANALYTIC, quantity="temp_peak", cost=1.0, id="t:badu", registry=mini.registry)
    def badu(subject: Subject, ctx: Any) -> ProducerOutput:
        return ProducerOutput(
            results=(interval_result("temp_peak", "K", 1.0, 1.0, 1.0, uncertainty_kind="exact"),)
        )

    mini.registry.load_modules([], mini.root)
    snap = mini.snapshot()
    s1 = snap.subjects["S1"]
    for pid in ("t:badq", "t:badu"):
        with pytest.raises(ProducerError):
            run_producer(mini.registry, pid, s1, snap, mini.root)


def test_unavailable_subject_and_missing_waiver_raise(mini: Any) -> None:
    snap = mini.snapshot()
    with pytest.raises(ProducerError):
        run_producer(mini.registry, P + "measure_temp", snap.subjects["S2"], snap, mini.root)
    assert DEFAULT_REGISTRY is mini.registry
