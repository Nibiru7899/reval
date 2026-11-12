"""P5-06: Tier B appliers (T6-B, T7, T8, T9, T12) on a tiny synthetic world project."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from bench.scenarios.model import APPLIERS, GenerateConfig, Scenario
from bench.scenarios.tier_b import (
    use_world,
    world_physical_params,
)
from bench.world import World
from bench.world.base import MEASUREMENTS_FILE
from tests.bench._impact import scenarios
from tests.bench._mini import copy_mini

CFG = {"t6_assumptions": ("A-flow-sens",)}


@pytest.fixture(autouse=True)
def world() -> Iterator[World]:
    w = World()
    use_world(w)
    yield w
    use_world(None)


def _synthetic(n: int = 4000) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    frames = []
    for pid in (1, 7):
        steps = n // 400
        w = np.repeat(rng.uniform(300, 4500, steps), 400)
        i_q = np.repeat(rng.uniform(-200, 250, steps), 400)
        frames.append(
            pd.DataFrame(
                {
                    "profile_id": pid,
                    "t": np.arange(n) * 0.5,
                    "motor_speed": w[:n],
                    "i_q": i_q[:n],
                    "i_d": -0.3 * np.abs(i_q[:n]),
                    "u_q": 0.02 * w[:n] + 0.1 * i_q[:n],
                    "u_d": -0.05 * np.abs(i_q[:n]),
                    "coolant": 28.0,
                    "ambient": 23.0,
                    "pm": 30.0,
                    "stator_yoke": 29.0,
                    "stator_tooth": 30.0,
                    "stator_winding": 31.0,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "data" / "processed").mkdir(parents=True)
    (root / "params").mkdir()
    _synthetic().to_parquet(root / "data" / "processed" / "measures.parquet", index=False)
    (root / "params" / "cooling.yaml").write_text("# comment\nflow_scale: 1.0\n", encoding="utf-8")
    subjects = {
        "DC-R01": {
            "kind": "duty_cycle",
            "generator": "motor.cycles:recorded",
            "params": {"profile_id": 7, "start_s": 100.0, "duration_s": 600.0},
        }
    }
    (root / "subjects.yaml").write_text(yaml.safe_dump(subjects), encoding="utf-8")
    manifest = {"assumptions": {"A-flow-sens": {"variable": "flow_scale", "bounds": [0.7, 1.3]}}}
    (root / "reval.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return root


def _tree(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != MEASUREMENTS_FILE
    }


def _table(root: Path) -> dict[str, dict[str, float]]:
    return json.loads((root / MEASUREMENTS_FILE).read_text(encoding="utf-8"))


def _sc(change_type: str, **cfg: object) -> Scenario:
    return scenarios(change_type, tier="B", n=1, **{**CFG, **cfg})[0]


def _neutral_table(root: Path, sc: Scenario) -> dict[str, dict[str, float]]:
    """The table the same scenario id would give on the unchanged plant (the S side of a CRN pair)."""
    same = sc.model_copy(update={"apply": "t6b_assumption", "params": {**_sc("T6").params}})
    APPLIERS[same.apply](root, same.model_copy(update={"id": sc.id}))
    return _table(root)


def test_t9_changes_no_declared_file_only_the_measurement_table(project: Path, tmp_path: Path) -> None:
    sc = _sc("T9")
    base = tmp_path / "base"
    base.mkdir()
    before = _tree(project)
    change = APPLIERS[sc.apply](project, sc)
    assert change.declared == []  # the change set is empty
    assert _tree(project) == before  # no file besides the undeclared table moved
    after = _table(project)
    assert set(after["DC-R01"]) == {"pm_peak", "sw_peak"}
    assert world_physical_params(sc).R_ic_scale == pytest.approx(sc.params["r_ic_scale"])
    # deterministic under the CRN seed (the scenario id)
    APPLIERS[sc.apply](project, sc)
    assert _table(project) == after


def test_t9_degradation_changes_the_world_not_the_noise(project: Path) -> None:
    sc = _sc("T9").model_copy(update={"params": {"r_ic_scale": 1.4}})
    APPLIERS[sc.apply](project, sc)
    degraded = _table(project)
    neutral = _neutral_table(project, sc)
    assert degraded != neutral  # R_ic moved the plant, the same noise draw sits on both


@pytest.mark.parametrize("ct", ["T7", "T8"])
def test_declared_flow_change_matches_the_world_change(project: Path, ct: str) -> None:
    sc = _sc(ct)
    change = APPLIERS[sc.apply](project, sc)
    factor = 1.0 + sc.params["flow_change"]
    assert change.declared == ["params/cooling.yaml"]
    text = (project / "params" / "cooling.yaml").read_text(encoding="utf-8")
    assert text.startswith("# comment\n") and f"flow_scale: {round(factor, 4)}" in text
    assert world_physical_params(sc).coolant_flow_scale == pytest.approx(factor)
    assert change.notes["flow_scale_new"] == pytest.approx(factor, abs=1e-4)
    assert _table(project) != _neutral_table(project, sc)


def test_t7_is_smaller_than_t8() -> None:
    small = scenarios("T7", tier="B", n=20)
    large = scenarios("T8", tier="B", n=20)
    assert max(abs(s.params["flow_change"]) for s in small) < min(abs(s.params["flow_change"]) for s in large)


def test_t6b_changes_the_assumption_but_not_the_plant(project: Path) -> None:
    sc = _sc("T6")
    assert sc.apply == "t6b_assumption" and sc.tier == "B"
    change = APPLIERS[sc.apply](project, sc)
    m = yaml.safe_load((project / "reval.yaml").read_text(encoding="utf-8"))
    assert m["assumptions"]["A-flow-sens"]["bounds"] == change.notes["new"] != [0.7, 1.3]
    assert world_physical_params(sc).coolant_flow_scale == 1.0


def test_t12_composes_physical_changes_and_writes_one_table(project: Path) -> None:
    t7 = _sc("T7")
    t9 = _sc("T9")
    comps = [
        {"change_type": "T7", "apply": t7.apply, "params": t7.params},
        {"change_type": "T9", "apply": t9.apply, "params": t9.params},
    ]
    sc = Scenario(
        id="B-T12-test",
        change_type="T12",
        tier="B",
        seed=1,
        base_snapshot=0,
        params={"components": comps},
        apply="t12_compound_b",
    )
    change = APPLIERS[sc.apply](project, sc)
    phys = world_physical_params(sc)
    assert phys.coolant_flow_scale == pytest.approx(1.0 + t7.params["flow_change"])
    assert phys.R_ic_scale == pytest.approx(t9.params["r_ic_scale"])
    assert change.declared == ["params/cooling.yaml"]
    assert len(change.notes["components"]) == 2
    assert _table(project)["DC-R01"]["pm_peak"] > 0


def test_t12_tier_b_generator_only_uses_applicable_components() -> None:
    cfg = GenerateConfig(instances_per_type=30, change_types=("T12",), tiers=("B",))
    from bench.scenarios.generate import generate

    for s in generate(cfg, 3):
        names = {c["change_type"] for c in s.params["components"]}
        assert names <= {"T5", "T6", "T7", "T8", "T9", "T10", "T11"}
        assert all(c["apply"] in APPLIERS for c in s.params["components"])


def test_t12_tier_a_compound_on_mini_applies_in_order(tmp_path: Path) -> None:
    t5 = scenarios("T5", n=1)[0]
    t11 = scenarios("T11", n=1)[0]
    comps = [
        {"change_type": "T5", "apply": t5.apply, "params": t5.params},
        {"change_type": "T11", "apply": t11.apply, "params": t11.params},
    ]
    sc = Scenario(
        id="A-T12-test",
        change_type="T12",
        tier="A",
        seed=1,
        base_snapshot=0,
        params={"components": comps},
        apply="t12_compound_a",
    )
    root = copy_mini(tmp_path)
    change = APPLIERS[sc.apply](root, sc)
    assert change.declared == ["reval.yaml", "mini/producers.py"]
    assert not change.retrain_targets and not change.retrain_lptn
