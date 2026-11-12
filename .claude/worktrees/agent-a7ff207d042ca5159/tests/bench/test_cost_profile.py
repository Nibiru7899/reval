"""P5-14: cost-sensitivity profiles tag rows and re-plan monotonically, reusing the producer cache."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from bench.run import RunConfig, load_config, load_cost_sensitivity, run_bench
from bench.scenarios.model import GenerateConfig

CONFIGS = Path(__file__).resolve().parents[2] / "bench" / "configs"
PROFILES = {"bench20": 20.0, "bench100": 100.0, "bench500": 500.0}

BASE = RunConfig(
    name="mini-cost",
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
)


def test_config_expands_to_the_three_profiles() -> None:
    cfgs = load_cost_sensitivity(CONFIGS / "cost_sensitivity.yaml")
    assert {c.cost_profile: c.bench_cost for c in cfgs} == PROFILES
    assert len({c.name for c in cfgs}) == 3
    # only the bench cost (and its tags) differ between profiles
    drop = {"name", "cost_profile", "bench_cost"}
    stripped = {json.dumps(c.model_dump(mode="json", exclude=drop), sort_keys=True) for c in cfgs}
    assert len(stripped) == 1
    assert load_config(CONFIGS / "smoke.yaml").bench_cost is None


def test_non_positive_bench_cost_rejected() -> None:
    with pytest.raises(ValueError):
        RunConfig.model_validate({**BASE.model_dump(mode="json"), "bench_cost": 0.0})


@pytest.mark.slow
def test_rows_tagged_and_bench_runs_monotone(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    frames = {}
    for tag, cost in PROFILES.items():
        cfg = BASE.model_copy(update={"name": f"mini-{tag}", "cost_profile": tag, "bench_cost": cost})
        out = run_bench(cfg, jobs=1, cache_dir=cache, results_root=tmp_path / tag)
        frames[tag] = pd.read_parquet(out / "rows.parquet")
        assert set(frames[tag]["cost_profile"]) == {tag}
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["failed"] == []

    def runs(tag: str) -> pd.Series:
        d = frames[tag]
        d = d[d["method"] == "reval"].drop_duplicates("scenario_id")
        return d.set_index("scenario_id")["n_bench_runs"]

    r20, r100, r500 = runs("bench20"), runs("bench100"), runs("bench500")
    assert (r100 <= r20).all() and (r500 <= r100).all()
    # B0 reruns everything, so its cost grows with the bench price: the profile reached the snapshot
    b0 = {t: f[f["method"] == "B0"].drop_duplicates("scenario_id")["cost"].sum() for t, f in frames.items()}
    assert b0["bench20"] < b0["bench100"] < b0["bench500"]
