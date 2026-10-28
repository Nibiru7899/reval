"""P5-03: Tier A appliers T1-T5 and the bench subset (motor data only under the data marker)."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from bench.scenarios.model import APPLIERS, SubsetConfig
from bench.scenarios.tier_a import (
    HYPERPARAMS_FILE,
    apply_base_variant,
    apply_scenario,
    apply_subset,
    base_variant,
    correct_pm,
    make_profile,
    select_subjects,
)
from reval.manifest.loader import load_manifest
from tests.bench._impact import impact, scenarios
from tests.bench._mini import copy_mini

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "motor_thermal"
PARQUET = EXAMPLE / "data" / "processed" / "measures.parquet"
SPLITS = yaml.safe_load((EXAMPLE / "splits.yaml").read_text(encoding="utf-8"))


def _frame(pid: int, n: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "profile_id": pid,
            "t": np.arange(n) * 0.5,
            "coolant": 25.0,
            "pm": 40.0,
            "stator_yoke": 38.0,
            "stator_tooth": 39.0,
            "stator_winding": 41.0,
            "ambient": 22.0,
            "motor_speed": 1000.0,
        }
    )


# --- pure pieces (no motor data) -------------------------------------------------------------------------
def test_make_profile_cuts_relabels_and_shifts_temperatures() -> None:
    src = _frame(8)
    same = make_profile(src, 99, 0.5)
    assert len(same) == 50 and set(same["profile_id"]) == {99}
    assert same["coolant"].eq(25.0).all()
    warm = make_profile(src, 99, 1.0, shift_k=10.0)
    assert warm["coolant"].eq(35.0).all() and warm["pm"].eq(50.0).all() and warm["ambient"].eq(22.0).all()
    assert src["coolant"].eq(25.0).all()  # the source is untouched


def test_correct_pm_touches_one_profile_only() -> None:
    df = pd.concat([_frame(1), _frame(2)], ignore_index=True)
    out = correct_pm(df, 2, -1.5)
    assert out.loc[out["profile_id"] == 2, "pm"].eq(38.5).all()
    assert out.loc[out["profile_id"] == 1, "pm"].eq(40.0).all()
    assert df["pm"].eq(40.0).all()
    assert out.drop(columns="pm").equals(df.drop(columns="pm"))


def test_base_variants_are_deterministic_and_cluster_zero_is_neutral() -> None:
    assert base_variant(0).neutral
    assert base_variant(5) == base_variant(5)
    assert len({repr(base_variant(i)) for i in range(30)}) > 10


def test_t5_moves_the_limit_and_nothing_else(tmp_path: Path) -> None:
    sc = scenarios("T5", n=1)[0]
    change, rep = impact(tmp_path, sc)
    assert change.declared == ["reval.yaml"]
    assert abs(change.notes["new"] - change.notes["old"] - sc.params["delta_k"]) < 1e-9
    assert "C-SHAFT" not in rep.affected_claims


def test_t5_unknown_requirement_fails_closed(tmp_path: Path) -> None:
    sc = scenarios("T5", n=1, t5_requirements=("R-NOPE",))[0]
    with pytest.raises(KeyError):
        APPLIERS[sc.apply](copy_mini(tmp_path), sc)


# --- the bench subset: manifest/subject files only, no data needed ----------------------------------------
@pytest.fixture
def subset_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "motor"
    shutil.copytree(EXAMPLE / "motor", dst / "motor", ignore=shutil.ignore_patterns("__pycache__"))
    for f in ("reval.yaml", "subjects.yaml"):
        shutil.copy(EXAMPLE / f, dst / f)
    return dst


def test_subset_has_53_claims_and_only_test_cycles(subset_copy: Path) -> None:
    chosen = apply_subset(subset_copy, SubsetConfig())
    m = yaml.safe_load((subset_copy / "reval.yaml").read_text(encoding="utf-8"))
    subjects = yaml.safe_load((subset_copy / "subjects.yaml").read_text(encoding="utf-8"))
    assert len(m["claims"]) == 12 * 2 + 12 * 2 + 4 + 1
    assert len(chosen["ood"]) == 3 and len(chosen["current_limit"]) == 4
    assert set(chosen["current_limit"]).isdisjoint(chosen["ood"])
    assert len(chosen["recorded"]) == 12
    for sid in chosen[
        "recorded"
    ]:  # recorded segments come from test profiles only; reserve is never a subject
        pid = subjects[sid]["params"]["profile_id"]
        assert pid in SPLITS["test"] and pid not in SPLITS["reserve"]
    lengths = {sum(b[2] for b in subjects[sid]["params"]["blocks"]) for sid in chosen["parametric"]}
    assert sorted(lengths) == [600, 1800, 3600]
    assert set(subjects) == set(chosen["recorded"]) | set(chosen["parametric"]) | {"SHAFT-1"}
    assert not [a for a in m["artifacts"] if a.endswith(("_ridge", "_mlp"))]
    assert "tpm_hgb" in m["artifacts"] and "uq_tsw_hgb" in m["artifacts"]
    assert '_ML_KINDS = ("hgb",)' in (subset_copy / "motor" / "producers.py").read_text(encoding="utf-8")


def test_subset_is_deterministic_and_loads_as_a_manifest(subset_copy: Path) -> None:
    subjects = yaml.safe_load((EXAMPLE / "subjects.yaml").read_text(encoding="utf-8"))
    assert select_subjects(subjects, SubsetConfig()) == select_subjects(subjects, SubsetConfig())
    apply_subset(subset_copy, SubsetConfig())
    model = load_manifest(subset_copy / "reval.yaml")
    assert len(model.claims) == 53


def test_base_variant_edits_limits_and_splits(subset_copy: Path) -> None:
    shutil.copy(EXAMPLE / "splits.yaml", subset_copy / "splits.yaml")
    v = next(
        base_variant(i)
        for i in range(1, 100)
        if base_variant(i).reserve_to_train and base_variant(i).pm_limit_delta_k
    )
    change = apply_base_variant(subset_copy, v)
    splits = yaml.safe_load((subset_copy / "splits.yaml").read_text(encoding="utf-8"))
    assert len(splits["reserve"]) == 2 and len(splits["train"]) == len(SPLITS["train"]) + 1
    m = yaml.safe_load((subset_copy / "reval.yaml").read_text(encoding="utf-8"))
    assert m["requirements"]["R-PM-MAX"]["limit"] == 90 + v.pm_limit_delta_k
    assert change.retrain_lptn and set(change.retrain_targets) == {"pm", "stator_winding"}


# --- motor data -------------------------------------------------------------------------------------------


def _workspace(tmp_path: Path) -> Path:
    """A private copy of the motor project with hardlinked data/models, as bench workspaces have."""
    from bench.harness.workspace import _copy_tree

    dst = tmp_path / "motor"
    shutil.copytree(
        EXAMPLE, dst, ignore=shutil.ignore_patterns("__pycache__", "data", "models", ".reval", "notebooks")
    )
    for d in ("data", "models"):
        _copy_tree(EXAMPLE / d, dst / d)
    return dst


@pytest.mark.data
@pytest.mark.skipif(not PARQUET.exists(), reason="processed motor data not available")
def test_t1_t2_t3_edit_the_data_without_touching_the_cache(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    before = pd.read_parquet(PARQUET)
    for ct in ("T1", "T2", "T3"):
        sc = scenarios(ct, n=1)[0]
        change = APPLIERS[sc.apply](root, sc)
        assert "data/processed/measures.parquet" in change.declared and change.retrain_lptn
    after = pd.read_parquet(root / "data" / "processed" / "measures.parquet")
    new_ids = sorted(set(after["profile_id"]) - set(before["profile_id"]))
    assert len(new_ids) == 2  # T1 and T2 each appended one profile
    splits = yaml.safe_load((root / "splits.yaml").read_text(encoding="utf-8"))
    assert set(new_ids) <= set(splits["train"]) and not set(new_ids) & set(splits["reserve"])
    assert pd.read_parquet(PARQUET).equals(before)  # the shared cache file was not modified in place


@pytest.mark.data
@pytest.mark.slow
@pytest.mark.skipif(not PARQUET.exists(), reason="processed motor data not available")
@pytest.mark.parametrize("ct", ["T1", "T4"])
def test_retraining_appliers_end_to_end_leave_the_cache_untouched(tmp_path: Path, ct: str) -> None:
    root = _workspace(tmp_path)
    cache_model = EXAMPLE / "models" / "tpm_hgb.joblib"
    stamp = (cache_model.stat().st_size, cache_model.stat().st_mtime_ns)
    sc = scenarios(ct, n=1)[0]
    if ct == "T4":
        sc = sc.model_copy(update={"params": {**sc.params, "target": "pm"}})
    t0 = time.perf_counter()
    change = apply_scenario(root, sc)
    print(f"{ct} apply+retrain: {time.perf_counter() - t0:.1f} s")
    assert (cache_model.stat().st_size, cache_model.stat().st_mtime_ns) == stamp
    assert (root / "models" / "uq_tpm_hgb.joblib").exists()
    if ct == "T4":
        assert (root / HYPERPARAMS_FILE).exists() and set(change.retrain_targets) == {"pm"}
