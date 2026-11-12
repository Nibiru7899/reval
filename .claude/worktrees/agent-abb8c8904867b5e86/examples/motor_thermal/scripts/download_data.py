"""Fetch the motor dataset anonymously (no Kaggle CLI, no credentials) and convert it to parquet."""

from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET_URL = "https://www.kaggle.com/api/v1/datasets/download/wkirgsn/electric-motor-temperature"
ARCHIVE_BYTES = 122_212_134
CSV_NAME = "measures_v2.csv"


def extract_csv(archive: Path, raw_dir: Path) -> Path:
    """Extract only measures_v2.csv from the archive, then delete the archive."""
    with zipfile.ZipFile(archive) as zf:
        member = next((n for n in zf.namelist() if Path(n).name == CSV_NAME), None)
        if member is None:
            raise SystemExit(f"{CSV_NAME} not found in {archive}")
        target = raw_dir / CSV_NAME
        with zf.open(member) as src, open(target, "wb") as dst:
            while chunk := src.read(1 << 20):
                dst.write(chunk)
    archive.unlink()
    return target


def download(raw_dir: Path) -> Path:
    """Stream the public archive, verify its exact size, and extract the CSV."""
    archive = raw_dir / "archive.zip"
    print(f"downloading {DATASET_URL}")
    with urllib.request.urlopen(DATASET_URL) as resp, open(archive, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    size = archive.stat().st_size
    if size != ARCHIVE_BYTES:
        archive.unlink()
        print(f"error: archive is {size} bytes, expected {ARCHIVE_BYTES}; deleted it", file=sys.stderr)
        raise SystemExit(1)
    return extract_csv(archive, raw_dir)


def ensure_raw_csv(raw_dir: Path) -> Path:
    """Return the raw CSV, downloading only when it is absent. Exactly one CSV must be present."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    csv = raw_dir / CSV_NAME
    if csv.exists():
        print(f"{csv} exists; skipping download")
    else:
        download(raw_dir)
    csvs = list(raw_dir.glob("*.csv"))
    if len(csvs) != 1:
        print(
            f"error: expected exactly one CSV in {raw_dir}, found {[c.name for c in csvs]}", file=sys.stderr
        )
        raise SystemExit(1)
    return csvs[0]


def main() -> None:
    from motor.data import prepare

    csv = ensure_raw_csv(ROOT / "data" / "raw")
    out = prepare(csv, ROOT / "data" / "processed" / "measures.parquet")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
