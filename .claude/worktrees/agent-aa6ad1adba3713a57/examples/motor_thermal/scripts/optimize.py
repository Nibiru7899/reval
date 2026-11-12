"""Run the design optimizer variants O1/O2/O3 and print/write the comparison (docs/04 A8).

Uses a trained trajectory model, its uq artifact (conformal + AD) and the drive map.
Bounds extend ``--bound-scale`` times past the train 99.5 percent quantile so that leaving the
applicability domain is possible; the result table says honestly whether it happened.
Writes models/optimizer_results.json (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from motor.cycles import blocks  # noqa: E402
from motor.models import load  # noqa: E402
from motor.optimizer import LIMIT_KEYS, energy_J, optimize  # noqa: E402
from motor.splits import load_splits, split_frame  # noqa: E402

from reval.uq.domain import ApplicabilityDomain  # noqa: E402


def _fmt(v: float | None, spec: str = ".1f") -> str:
    return "inf" if v is None else format(v, spec)


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-artifact", default="tpm_hgb")
    ap.add_argument("--variants", nargs="+", default=["O1", "O2", "O3"], choices=["O1", "O2", "O3"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--bound-scale", type=float, default=1.25)
    ap.add_argument("--popsize", type=int, default=15)
    ap.add_argument("--maxiter", type=int, default=50)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "processed" / "measures.parquet")
    ap.add_argument("--splits", type=Path, default=ROOT / "splits.yaml")
    ap.add_argument("--models-dir", type=Path, default=ROOT / "models")
    ap.add_argument("--limits", type=Path, default=ROOT / "params" / "limits.yaml")
    ap.add_argument("--out", type=Path, default=None, help="default: <models-dir>/optimizer_results.json")
    args = ap.parse_args(argv)

    model = load(args.models_dir / f"{args.model_artifact}.joblib")
    art = joblib.load(args.models_dir / f"uq_{args.model_artifact}.joblib")
    ad = ApplicabilityDomain.from_dict(art["ad"])
    drive_map = joblib.load(args.models_dir / "drive_map.joblib")
    limits = yaml.safe_load(args.limits.read_text(encoding="utf-8"))
    train = split_frame(pd.read_parquet(args.data), load_splits(args.splits), "train")
    q_t = float(train["torque"].quantile(0.995))
    q_w = float(train["motor_speed"].quantile(0.995))
    bounds = [(0.0, args.bound_scale * q_t), (0.0, args.bound_scale * q_w)] * 3

    results: dict[str, Any] = {}
    rows = []
    for v in args.variants:
        t0 = time.time()
        r = optimize(
            v,  # type: ignore[arg-type]
            model, art["conformal"], ad, drive_map, limits, bounds, seed=args.seed,
            popsize=args.popsize, maxiter=args.maxiter,
        )  # fmt: skip
        secs = time.time() - t0
        cyc = blocks(r.subject_params)
        dm_rep = drive_map.domain_report(cyc["torque"].to_numpy(), cyc["motor_speed"].to_numpy())
        results[v] = {
            "theta": r.theta.tolist(),
            "subject_params": r.subject_params,
            "energy_MJ": energy_J(r.theta) / 1e6,
            "pred_peak_degC": r.pred_peak,
            "upper_degC": r.upper,
            "model_ad": r.ad_report.to_dict() | {"box": None},
            "drive_map_ad": dm_rep.to_dict() | {"box": None},
            "seconds": round(secs, 1),
        }
        rows.append((v, r, dm_rep, secs))

    head = next(t for t in model.targets if t in LIMIT_KEYS)
    out: dict[str, Any] = {
        "model_artifact": args.model_artifact,
        "target": head,
        "limit_degC": float(limits[LIMIT_KEYS[head]]),
        "seed": args.seed,
        "bound_scale": args.bound_scale,
        "bounds": bounds,
        "variants": results,
    }
    path = args.out or args.models_dir / "optimizer_results.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"target={head} limit={out['limit_degC']} degC model={args.model_artifact} seed={args.seed}")
    print("var  theta[T Nm, w rpm x3]                    energy MJ  peak  upper  model-AD  frac_out  dm-AD")
    for v, r, dm_rep, _ in rows:
        th = " ".join(f"{x:7.1f}" for x in np.asarray(r.theta))
        print(
            f"{v}   {th}  {results[v]['energy_MJ']:8.2f}  {r.pred_peak:5.1f}  {_fmt(r.upper):>5}  "
            f"{'in' if r.ad_report.inside else 'OUT':>8}  {r.ad_report.frac_outside:8.3f}  "
            f"{'in' if dm_rep.inside else 'OUT'}"
        )  # fmt: skip
    print(f"wrote {path}")
    return out


if __name__ == "__main__":
    main()
