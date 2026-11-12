"""Fit the conformal and applicability-domain artifacts for one trained model.

This is the only place these uq artifacts are produced; later tasks read them without recalibrating.
Calibration uses ``calib`` profiles only; the AD box comes from ``train`` (AGENTS rule 6).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib  # noqa: E402
import pandas as pd  # noqa: E402
from motor.conformal import PeakConformal  # noqa: E402
from motor.features import make_features  # noqa: E402
from motor.models import load  # noqa: E402
from motor.splits import load_splits, split_frame  # noqa: E402

from reval.uq.domain import ApplicabilityDomain  # noqa: E402


def main(argv: Sequence[str] | None = None) -> Path:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-artifact", required=True, help="artifact id, e.g. tpm_ridge")
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "processed" / "measures.parquet")
    ap.add_argument("--splits", type=Path, default=ROOT / "splits.yaml")
    ap.add_argument("--models-dir", type=Path, default=ROOT / "models")
    ap.add_argument(
        "--max-calib-rows",
        type=int,
        default=20_000,
        help="strided subsample of calib rows for the AD distance threshold (kNN is slow on all rows)",
    )
    args = ap.parse_args(argv)

    model_path = args.models_dir / f"{args.model_artifact}.joblib"
    model = load(model_path)
    df = pd.read_parquet(args.data)
    splits = load_splits(args.splits)
    train = split_frame(df, splits, "train")
    calib = split_frame(df, splits, "calib")

    conformal = PeakConformal().fit(model, calib, args.alpha)
    x_train = make_features(train)[0][model.feature_names].to_numpy(dtype=float)
    x_calib = make_features(calib)[0][model.feature_names].to_numpy(dtype=float)
    stride = max(1, -(-len(x_calib) // args.max_calib_rows))
    ad = ApplicabilityDomain(model.feature_names).fit(x_train, x_calib[::stride])

    meta = {
        "alpha": args.alpha,
        "split_hash": hashlib.sha256(args.splits.read_bytes()).hexdigest(),
        "model_hash": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "model_artifact": args.model_artifact,
        "ad_calib_stride": stride,
        "calib_profiles": list(splits.calib),
        "n_windows": {f"{t}/{c}": sc.n for (t, c), sc in conformal.conformal.items()},
        "q": {f"{t}/{c}": sc.q for (t, c), sc in conformal.conformal.items()},
    }
    out = args.models_dir / f"uq_{args.model_artifact}.joblib"
    joblib.dump({"conformal": conformal, "ad": ad.to_dict(), "meta": meta}, out)
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    print(f"{out.name}: n_windows={meta['n_windows']} q={meta['q']}")
    return out


if __name__ == "__main__":
    main()
