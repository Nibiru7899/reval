"""Train one trajectory model on the ``train`` split only; writes models/t{pm,sw}_<model>.joblib."""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from motor.models import TARGETS, TrajectoryModel, evaluate, save  # noqa: E402
from motor.splits import load_splits, split_frame  # noqa: E402

PREFIX = {"pm": "tpm", "stator_winding": "tsw"}
WINDOW_ROWS = 3600  # 30 min at 2 Hz, for the sidecar peak metric
MLP_HYPERPARAMS = {"hidden_layer_sizes": (32,), "max_iter": 30, "batch_size": 2048}


def main(argv: Sequence[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", choices=["ridge", "hgb", "mlp"], required=True)
    ap.add_argument("--target", choices=list(TARGETS), required=True)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "processed" / "measures.parquet")
    ap.add_argument("--splits", type=Path, default=ROOT / "splits.yaml")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "models")
    ap.add_argument("--max-iter", type=int, default=None, help="override MLP max_iter")
    args = ap.parse_args(argv)

    df = pd.read_parquet(args.data)
    splits = load_splits(args.splits)
    train = split_frame(df, splits, "train")
    test = split_frame(df, splits, "test")
    hp = dict(MLP_HYPERPARAMS) if args.model == "mlp" else {}
    if args.model == "mlp" and args.max_iter:
        hp["max_iter"] = args.max_iter
    model = TrajectoryModel(args.model, targets=(args.target,), **hp)
    t0 = time.time()
    model.fit(train)
    fit_s = time.time() - t0
    metrics = evaluate(model, test, WINDOW_ROWS)
    path = args.out_dir / f"{PREFIX[args.target]}_{args.model}.joblib"
    meta = {
        "split_hash": hashlib.sha256(args.splits.read_bytes()).hexdigest(),
        "train_profiles": list(splits.train),
        "train_rows": len(train),
        "fit_seconds": round(fit_s, 1),
        "hyperparams": hp,
        "metrics_test": metrics,
        "window_rows": WINDOW_ROWS,
    }
    save(model, path, meta=meta)
    print(f"{path.name}: fit {fit_s:.0f}s, test {metrics[args.target]}")
    return path


if __name__ == "__main__":
    main()
