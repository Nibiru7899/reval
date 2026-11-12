"""Identify the LPTN on `train`, report MSE and model-form bands on `test`.

Writes params/lptn.yaml (committed) and models/lptn_report.json (git-ignored).
Run: .venv/Scripts/python examples/motor_thermal/scripts/calibrate_lptn.py [--max-profiles 12] [--max-nfev 80]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from motor import lptn  # noqa: E402
from motor.splits import load_splits, split_frame  # noqa: E402

WINDOW_ROWS = {"short": 1200, "medium": 3600, "long": 7200}  # 10 / 30 / 60 min at 2 Hz


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-profiles", type=int, default=30)
    ap.add_argument("--max-nfev", type=int, default=80)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    parquet = ROOT / "data" / "processed" / "measures.parquet"
    splits_path = ROOT / "splits.yaml"
    params_path = ROOT / "params" / "lptn.yaml"
    df = pd.read_parquet(parquet)
    splits = load_splits(splits_path)
    train, calib, test = (split_frame(df, splits, n) for n in ("train", "calib", "test"))

    fitted, info = lptn.identify(
        train,
        lptn.default_params(),
        {},
        max_profiles=args.max_profiles,
        seed=args.seed,
        max_nfev=args.max_nfev,
    )
    lptn.dump_params(fitted, params_path)
    print(f"identified in {info['runtime_s']:.0f} s, nfev={info['nfev']}, MSE {info['mse_train']}")

    mse = {
        name: lptn.evaluate_mse(fitted, frame)
        for name, frame in (("train", train), ("calib", calib), ("test", test))
    }
    bands = {k: lptn.model_form_band(fitted, test, w) for k, w in WINDOW_ROWS.items()}
    report = {
        "n_nodes": 4,
        "mse_K2": mse,
        "mse_K2_test_mean": sum(mse["test"].values()) / len(mse["test"]),
        "model_form_band_K": bands,
        "window_rows": WINDOW_ROWS,
        "identification": info,
        "inputs": {
            "parquet_sha256": sha256(parquet),
            "splits_sha256": sha256(splits_path),
            "params_sha256": sha256(params_path),
        },
        "note": "MSE: 10 s block means, measured initial state; bands: 0.5 s simulation.",
    }
    out = ROOT / "models" / "lptn_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"mse_K2": mse, "bands": bands}, indent=2))


if __name__ == "__main__":
    main()
