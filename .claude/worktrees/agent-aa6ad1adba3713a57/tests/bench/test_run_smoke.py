"""P5-11: the bench runner on a 2-scenario mini-project config (resumable, cached, worker-count invariant)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from bench.run import RunConfig, config_hash, run_bench
from bench.scenarios.model import GenerateConfig

pytestmark = pytest.mark.slow

CFG = RunConfig(
    name="mini-smoke",
    project="tests/fixtures/mini_project",
    motor=False,
    seed=0,
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


def _timings(results: Path) -> list[dict]:
    lines = (results / "timings.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines]


def test_runner_is_cached_resumable_and_deterministic(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    first = run_bench(CFG, jobs=1, cache_dir=cache, results_root=tmp_path / "r1")
    assert first.name == config_hash(CFG)
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["n_completed"] == 2 and manifest["failed"] == []
    rows = pd.read_parquet(first / "rows.parquet")
    claims = 4
    assert len(rows) == 2 * len(CFG.methods) * claims
    assert set(rows["method"]) == set(CFG.methods)
    # B3 never runs anything; B0 pays for everything
    assert (rows.loc[rows["method"] == "B3", "cost"] == 0).all()
    assert (rows.loc[rows["method"] == "B0", "cost"] == rows.loc[rows["method"] == "B0", "b0_cost"]).all()
    sha1 = (first / "rows.sha256").read_text(encoding="utf-8")

    # rerun into a fresh results dir with the same producer cache and two workers: hits, identical rows
    second = run_bench(CFG, jobs=2, cache_dir=cache, results_root=tmp_path / "r2")
    assert (second / "rows.sha256").read_text(encoding="utf-8") == sha1
    t2 = _timings(second)
    assert all(t["ok"] for t in t2)
    assert sum(t["cache_hits"] for t in t2) > 0
    assert sum(t["cache_misses"] for t in t2) == 0

    # resuming the first results dir skips every completed scenario
    run_bench(CFG, jobs=1, cache_dir=cache, results_root=tmp_path / "r1")
    assert len(_timings(first)) == 2  # nothing new was run
    assert (first / "rows.sha256").read_text(encoding="utf-8") == sha1
