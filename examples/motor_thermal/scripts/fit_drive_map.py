"""Fit the drive map on train profiles; write models/drive_map.joblib and report held-out R^2."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "src"))

import joblib  # noqa: E402
import pandas as pd  # noqa: E402
from motor.drive_map import DriveMap  # noqa: E402
from motor.splits import load_splits, split_frame  # noqa: E402


def main() -> None:
    df = pd.read_parquet(ROOT / "data" / "processed" / "measures.parquet")
    splits = load_splits(ROOT / "splits.yaml")
    dm = DriveMap().fit(split_frame(df, splits, "train"))
    out = ROOT / "models" / "drive_map.joblib"
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(dm, out)
    report = {
        "test_steady": dm.r2(split_frame(df, splits, "test")),
        "test_all_rows": dm.r2(split_frame(df, splits, "test"), steady_only=False),
    }
    (out.parent / "drive_map_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
