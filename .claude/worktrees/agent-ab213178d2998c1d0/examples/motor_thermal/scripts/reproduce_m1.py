"""Reproduce the M1 milestone end to end and write ``models/m1_report.json`` (docs/07 M1 DoD).

Pipeline: prepare data -> splits check -> train M1-M3 (both targets) -> calibrate -> coverage tables
(alpha 0.1 and 0.05) -> LPTN identification report -> drive map -> optimizer O1/O2/O3.
Existing artifacts are reused unless ``--force``. ``--quick`` runs a tiny version (a few profiles, ridge
only, small ``max_nfev``) in its own output directory and never touches the committed params or the
real artifacts. Every number in the report is computed here or copied from the scripts' outputs.
Wall-clock timings go to ``m1_timings.json`` so that the report hash is stable across reruns.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sklearn  # noqa: E402
import yaml  # noqa: E402
from motor import lptn  # noqa: E402
from motor.conformal import LENGTH_CLASSES, PeakConformal  # noqa: E402
from motor.drive_map import DriveMap  # noqa: E402
from motor.models import TARGETS, evaluate, load, peaks  # noqa: E402
from motor.splits import Splits, load_splits, save_splits, split_frame  # noqa: E402

KINDS = ("ridge", "hgb", "mlp")
PREFIX = {"pm": "tpm", "stator_winding": "tsw"}
ALPHAS = (0.1, 0.05)
WINDOW_ROWS = 3600  # 30 min at 2 Hz, the evaluation window of train.py
DISCLAIMER = (
    "Study results on one public dataset. They state what the recorded evidence supports against "
    "declared study limits; they are not a safety, certification or standards claim."
)


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_m1_{name}", ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clean(o: Any) -> Any:
    """JSON-safe copy: NaN/inf -> None, numpy scalars -> python."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, np.generic):
        return _clean(o.item())
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


class _Timer:
    def __init__(self) -> None:
        self.t: dict[str, float] = {}

    def run(self, name: str, fn: Any, *a: Any, **k: Any) -> Any:
        t0 = time.time()
        print(f"[m1] {name} ...", flush=True)
        out = fn(*a, **k)
        self.t[name] = round(time.time() - t0, 1)
        print(f"[m1] {name} done in {self.t[name]} s", flush=True)
        return out


def _quick_subset(df: pd.DataFrame, splits: Splits, workdir: Path) -> tuple[Path, Path]:
    """Small parquet + splits file: the smallest profiles (>= one 30-min window if possible) per split."""
    rows = df.groupby("profile_id").size()

    def pick(ids: Sequence[int], n: int) -> tuple[int, ...]:
        big = [i for i in ids if rows[i] >= WINDOW_ROWS] or list(ids)
        return tuple(sorted(sorted(big, key=lambda i: (rows[i], i))[:n]))

    sub = Splits(
        train=pick(splits.train, 6), calib=pick(splits.calib, 3), test=pick(splits.test, 2), reserve=()
    )
    keep = [*sub.train, *sub.calib, *sub.test]
    workdir.mkdir(parents=True, exist_ok=True)
    data_path, splits_path = workdir / "measures_quick.parquet", workdir / "splits_quick.yaml"
    df[df["profile_id"].isin(keep)].reset_index(drop=True).to_parquet(data_path)
    save_splits(sub, splits_path, seed=0, source_note="reproduce_m1 --quick subset (not the study split)")
    return data_path, splits_path


def _coverage_tables(
    models_dir: Path, kinds: Sequence[str], calib: pd.DataFrame, test: pd.DataFrame
) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for alpha in ALPHAS:
        per_art: dict[str, Any] = {}
        for target in TARGETS:
            for kind in kinds:
                art = f"{PREFIX[target]}_{kind}"
                model = load(models_dir / f"{art}.joblib")
                pc = PeakConformal().fit(model, calib, alpha)
                cov = pc.coverage(model, test)[target]
                per_art[art] = {
                    cls: {
                        "q_K": pc.conformal[(target, cls)].q,
                        "n_calib_windows": pc.conformal[(target, cls)].n,
                        "n_test_windows": len(peaks(test[target], test["profile_id"], rows)),
                        "empirical_coverage": cov[cls],
                    }
                    for cls, rows in LENGTH_CLASSES.items()
                }
        tables[f"alpha_{alpha}"] = per_art
    return tables


def _lptn_quick(train: pd.DataFrame, test: pd.DataFrame, out_dir: Path) -> dict[str, Any]:
    fitted, info = lptn.identify(train, lptn.default_params(), {}, max_profiles=3, seed=0, max_nfev=5)
    mse = lptn.evaluate_mse(fitted, test)
    report = {
        "mse_K2": {"test": mse},
        "mse_K2_test_mean": sum(mse.values()) / len(mse),
        "model_form_band_K": {k: lptn.model_form_band(fitted, test, w) for k, w in LENGTH_CLASSES.items()},
        "identification": {k: v for k, v in info.items() if k != "runtime_s"},
    }
    (out_dir / "lptn_report.json").write_text(json.dumps(_clean(report), indent=2), encoding="utf-8")
    return report


def _fit_drive_map(train: pd.DataFrame, test: pd.DataFrame, models_dir: Path) -> dict[str, Any]:
    dm = DriveMap().fit(train)
    joblib.dump(dm, models_dir / "drive_map.joblib")
    report = {"test_steady": dm.r2(test), "test_all_rows": dm.r2(test, steady_only=False)}
    (models_dir / "drive_map_report.json").write_text(json.dumps(_clean(report), indent=2), encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="tiny run: few profiles, ridge only, small max_nfev")
    ap.add_argument("--force", action="store_true", help="recompute artifacts even when present")
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "processed" / "measures.parquet")
    ap.add_argument("--splits", type=Path, default=ROOT / "splits.yaml")
    ap.add_argument("--models-dir", type=Path, default=None, help="default: models/ (quick: required)")
    ap.add_argument("--limits", type=Path, default=ROOT / "params" / "limits.yaml")
    args = ap.parse_args(argv)
    if args.quick and args.models_dir is None:
        ap.error("--quick needs --models-dir (a scratch directory; the real artifacts are never touched)")
    models_dir: Path = args.models_dir or ROOT / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    timer = _Timer()
    kinds = ("ridge",) if args.quick else KINDS
    data_path, splits_path = args.data, args.splits

    # 1. prepare
    if not data_path.exists():
        timer.run("prepare", _script("download_data").main)
    df_full = pd.read_parquet(data_path)

    # 2. splits check (load_splits asserts pairwise disjointness)
    splits = load_splits(splits_path)
    if args.quick:
        data_path, splits_path = _quick_subset(df_full, splits, models_dir)
        df_full = pd.read_parquet(data_path)
        splits = load_splits(splits_path)
    train, calib, test = (split_frame(df_full, splits, n) for n in ("train", "calib", "test"))
    present = set(df_full["profile_id"].unique())
    assert present >= set(splits.train) | set(splits.calib) | set(splits.test)

    # 3. train M1-M3, both targets
    train_s = _script("train")
    for target in TARGETS:
        for kind in kinds:
            art = f"{PREFIX[target]}_{kind}"
            if args.force or not (models_dir / f"{art}.joblib").exists():
                timer.run(
                    f"train {art}",
                    train_s.main,
                    ["--model", kind, "--target", target, "--data", str(data_path),
                     "--splits", str(splits_path), "--out-dir", str(models_dir)],
                )  # fmt: skip

    # 4. calibrate (alpha 0.1 artifacts; the alpha table below recomputes in memory)
    cal_s = _script("calibrate")
    for target in TARGETS:
        for kind in kinds:
            art = f"{PREFIX[target]}_{kind}"
            if args.force or not (models_dir / f"uq_{art}.joblib").exists():
                timer.run(
                    f"calibrate {art}",
                    cal_s.main,
                    ["--model-artifact", art, "--data", str(data_path), "--splits", str(splits_path),
                     "--models-dir", str(models_dir)],
                )  # fmt: skip

    # 5. model metrics and coverage tables (computed fresh from the artifacts)
    metrics: dict[str, Any] = {}
    for target in TARGETS:
        for kind in kinds:
            art = f"{PREFIX[target]}_{kind}"
            metrics[art] = evaluate(load(models_dir / f"{art}.joblib"), test, WINDOW_ROWS)[target]
    coverage = timer.run("coverage tables", _coverage_tables, models_dir, kinds, calib, test)

    # 6. LPTN
    lptn_path = models_dir / "lptn_report.json"
    if args.quick:
        lptn_report = timer.run("lptn (quick)", _lptn_quick, train, test, models_dir)
    else:
        if args.force or not lptn_path.exists():
            old_argv = sys.argv
            sys.argv = ["calibrate_lptn"]  # the script parses sys.argv and writes params/lptn.yaml
            try:
                timer.run("lptn identify", _script("calibrate_lptn").main)
            finally:
                sys.argv = old_argv
        lptn_report = json.loads(lptn_path.read_text(encoding="utf-8"))

    # 7. drive map
    dm_path = models_dir / "drive_map.joblib"
    if args.force or args.quick or not dm_path.exists():
        dm_report = timer.run("drive map", _fit_drive_map, train, test, models_dir)
    else:
        dm_report = json.loads((models_dir / "drive_map_report.json").read_text(encoding="utf-8"))

    # 8. optimizer
    opt_path = models_dir / "optimizer_results.json"
    if args.force or args.quick or not opt_path.exists():
        opt_art = "tpm_ridge" if args.quick else "tpm_hgb"
        opt_args = ["--model-artifact", opt_art, "--data", str(data_path), "--splits", str(splits_path),
                    "--models-dir", str(models_dir), "--limits", str(args.limits)]  # fmt: skip
        if args.quick:
            opt_args += ["--maxiter", "2", "--popsize", "4"]
        timer.run("optimize", _script("optimize").main, opt_args)
    opt = json.loads(opt_path.read_text(encoding="utf-8"))
    for v in opt["variants"].values():
        v.pop("seconds", None)  # wall-clock is kept out of the hashed report

    inputs = {
        "parquet_sha256": sha256(data_path),
        "splits_sha256": sha256(splits_path),
        "limits_sha256": sha256(args.limits),
        "lptn_params_sha256": sha256(ROOT / "params" / "lptn.yaml"),
        "cooling_sha256": sha256(ROOT / "params" / "cooling.yaml"),
    }
    artifacts = {
        p.name: sha256(p)
        for p in sorted(models_dir.glob("*.joblib"))
        if p.stem.split("_")[0] in {"tpm", "tsw", "uq", "drive"}
    }
    report = _clean(
        {
            "mode": "quick" if args.quick else "full",
            "disclaimer": DISCLAIMER,
            "inputs": inputs,
            "artifact_sha256": artifacts,
            "environment": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "scikit_learn": sklearn.__version__,
            },
            "splits": {n: list(getattr(splits, n)) for n in ("train", "calib", "test", "reserve")},
            "limits": yaml.safe_load(args.limits.read_text(encoding="utf-8")),
            "window_rows_metrics": WINDOW_ROWS,
            "model_test_metrics": metrics,
            "alphas": list(ALPHAS),
            "coverage_tables": coverage,
            "lptn": lptn_report,
            "drive_map_r2": dm_report,
            "optimizer": opt,
        }
    )
    out = models_dir / "m1_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (models_dir / "m1_timings.json").write_text(json.dumps(timer.t, indent=2), encoding="utf-8")
    print(f"[m1] wrote {out}\n[m1] sha256 {sha256(out)}")
    return out


if __name__ == "__main__":
    main()
