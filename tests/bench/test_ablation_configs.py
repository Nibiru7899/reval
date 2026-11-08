"""P5-13: every ablation config loads, and each ablation runs end to end on the mini project."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bench.run import RunConfig, load_config, run_bench
from bench.scenarios.model import GenerateConfig
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings

ABLATIONS = Path(__file__).resolve().parents[2] / "bench" / "configs" / "ablations"
EXPECTED = {
    "a1_no_field_selectors": {"field_level_selectors": False},
    "a2_no_carry_forward": {"tolerance_carry_forward": False},
    "a3_no_scope": {"scope_freshness": False},
    "a6_greedy": {"planner": "greedy"},
    "a7_kappa": {"kappa_override": 1.0},
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_ablation_config_changes_only_its_switch(name: str) -> None:
    cfg = load_config(ABLATIONS / f"{name}.yaml")
    assert cfg.settings == DEFAULT_SETTINGS.model_copy(update=EXPECTED[name])
    assert cfg.name == name


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_ablation_runs_on_mini_project(name: str, tmp_path: Path) -> None:
    cfg = RunConfig(
        name=name,
        project="tests/fixtures/mini_project",
        motor=False,
        generate=GenerateConfig(
            instances_per_type=1,
            n_base_snapshots=1,
            tiers=("A",),
            change_types=("T5", "T10"),
            t5_requirements=("R-TEMP",),
            t6_assumptions=("A-ambient",),
        ),
        epsilon={"temp_peak": 0.5, "shaft_d": 0.0},
        settings=ReValSettings(**EXPECTED[name]),
    )
    out = run_bench(cfg, jobs=1, cache_dir=tmp_path / "cache", results_root=tmp_path / "r")
    rows = pd.read_parquet(out / "rows.parquet")
    assert not rows.empty and "reval" in set(rows["method"])
