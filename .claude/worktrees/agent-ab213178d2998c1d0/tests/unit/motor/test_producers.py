"""P2-13: producer metadata and manifest consistency (no dataset needed)."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from reval.domain.engineering import Subject
from reval.domain.evidence import Producer, ProducerKind
from reval.domain.selectors import Selector
from reval.manifest import load_manifest
from reval.sdk import DEFAULT_REGISTRY

ROOT = Path(__file__).resolve().parents[3] / "examples" / "motor_thermal"


@pytest.fixture
def producers() -> Iterator[None]:
    import motor.producers

    DEFAULT_REGISTRY.clear()
    importlib.reload(motor.producers)
    yield
    DEFAULT_REGISTRY.clear()


def _meta(pid: str) -> Producer:
    return DEFAULT_REGISTRY.get(pid).meta


def test_binding_names_and_kinds(producers: None) -> None:
    ids = {rp.meta.id: rp.meta for rp in DEFAULT_REGISTRY.all()}
    base = {"lptn_sim", "bench_measure", "shaft_check", "current_limit_check"}
    assert base <= set(ids) and len(ids) == len(base) + 6  # + six ML predictors (P4-03)
    assert ids["lptn_sim"].kind is ProducerKind.PHYSICS_SIM
    assert (ids["lptn_sim"].fidelity, ids["lptn_sim"].cost) == (2, 5)
    assert ids["bench_measure"].kind is ProducerKind.MEASUREMENT
    assert (ids["bench_measure"].fidelity, ids["bench_measure"].cost) == (3, 100)
    assert ids["shaft_check"].kind is ProducerKind.ANALYTIC
    assert ids["current_limit_check"].kind is ProducerKind.ANALYTIC
    assert ids["current_limit_check"].fidelity == 3  # needed for the medium policy's analytic clause


def test_lptn_sim_dependencies_are_pointer_level(producers: None) -> None:
    meta = _meta("lptn_sim")
    assert meta.predictors == ("lptn",)
    deps = set(meta.depends_on)
    assert {"lptn#/R", "lptn#/C", "lptn#/loss", "drive_map", "cooling#/flow_scale"} <= deps
    assert "lptn" not in deps  # never the whole artifact (tolerances need pointer deps)


def test_bench_measure_depends_on_measured_columns_and_flow(producers: None) -> None:
    meta = _meta("bench_measure")
    assert set(meta.depends_on) == {"measures[pm,stator_winding]", "cooling#/flow_scale"}
    assert set(meta.assumes) == {"A-sensor-pm", "A-sensor-sw"}
    assert meta.predictors == ()


def test_availability_predicates(producers: None) -> None:
    recorded = Subject(id="r", kind="duty_cycle", generator="motor.cycles:recorded", params={})
    blocks = Subject(id="p", kind="duty_cycle", generator="motor.cycles:blocks", params={})
    design = Subject(id="d", kind="design")
    bench = DEFAULT_REGISTRY.get("bench_measure").available_for
    assert bench is not None and bench(recorded) and not bench(blocks) and not bench(design)
    shaft = DEFAULT_REGISTRY.get("shaft_check").available_for
    assert shaft is not None and shaft(design) and not shaft(blocks)
    sim = DEFAULT_REGISTRY.get("lptn_sim").available_for
    assert sim is not None and sim(recorded) and sim(blocks) and not sim(design)


def test_manifest_loads_and_is_consistent_with_limits() -> None:
    m = load_manifest(ROOT / "reval.yaml")
    limits = yaml.safe_load((ROOT / "params" / "limits.yaml").read_text(encoding="utf-8"))
    assert m.requirements["R-PM-MAX"].limit == limits["pm_peak_limit_degC"]
    assert m.requirements["R-SW-MAX"].limit == limits["sw_peak_limit_degC"]
    assert m.requirements["R-IS-MAX"].limit == limits["inverter_current_limit_A"]
    assert m.requirements["R-SHAFT-D"].limit == limits["shaft_d_limit_mm"]
    crit = {k: v.criticality.value for k, v in m.requirements.items()}
    assert crit == {"R-PM-MAX": "high", "R-SW-MAX": "medium", "R-IS-MAX": "medium", "R-SHAFT-D": "low"}
    assert len(m.subjects) == 81
    by_req = {r: [c for c in m.claims if c.requirement == r] for r in m.requirements}
    assert len(by_req["R-PM-MAX"]) == len(by_req["R-SW-MAX"]) == 80
    assert [c.id for c in by_req["R-SHAFT-D"]] == ["C-SHAFT"]
    assert len(by_req["R-IS-MAX"]) >= 1
    for name in ("tpm", "tsw"):
        for model in ("ridge", "hgb", "mlp"):
            assert m.artifacts[f"{name}_{model}"].derived_from == ("measures", "splits")


def test_pointer_dependencies_resolve_in_the_param_files(producers: None) -> None:
    m = load_manifest(ROOT / "reval.yaml")
    for rp in DEFAULT_REGISTRY.all():
        for text in rp.meta.depends_on:
            sel = Selector.parse(text)
            assert sel.artifact_id in m.artifacts, text
            if sel.pointer is None:
                continue
            path = ROOT / m.artifacts[sel.artifact_id].path
            if not path.exists():  # e.g. the git-ignored models/lptn_report.json
                continue
            node = yaml.safe_load(path.read_text(encoding="utf-8"))
            for seg in sel.pointer.split("/")[1:]:
                assert seg in node, f"{text}: {seg!r} missing in {path.name}"
                node = node[seg]
