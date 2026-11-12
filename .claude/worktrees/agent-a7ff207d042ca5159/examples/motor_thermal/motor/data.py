"""Load, validate and convert the Paderborn motor temperature dataset (docs/05 §1)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from reval.errors import SchemaError

EXPECTED_COLUMNS: tuple[str, ...] = (
    "u_q",
    "coolant",
    "stator_winding",
    "u_d",
    "stator_tooth",
    "motor_speed",
    "i_d",
    "i_q",
    "pm",
    "stator_yoke",
    "ambient",
    "torque",
    "profile_id",
)

SAMPLE_PERIOD_S = 0.5  # the dataset is recorded at 2 Hz


def _check_columns(df: pd.DataFrame) -> None:
    present = set(df.columns)
    missing = sorted(set(EXPECTED_COLUMNS) - present)
    extra = sorted(present - set(EXPECTED_COLUMNS))
    if missing or extra:
        raise SchemaError(f"unexpected columns: missing={missing}, extra={extra}")


def load_raw(path: Path) -> pd.DataFrame:
    """Read the raw CSV; the column set must match EXPECTED_COLUMNS (order-insensitive)."""
    df = pd.read_csv(path)
    _check_columns(df)
    return df


def validate(df: pd.DataFrame) -> None:
    """Raise SchemaError on missing columns, NaNs, non-integer profile_id or an empty frame."""
    _check_columns(df)
    if len(df) == 0:
        raise SchemaError("frame has no rows")
    nan_cols = [c for c in EXPECTED_COLUMNS if df[c].isna().any()]
    if nan_cols:
        raise SchemaError(f"NaN values in columns: {nan_cols}")
    if not pd.api.types.is_integer_dtype(df["profile_id"]):
        raise SchemaError(f"profile_id must be integer, got {df['profile_id'].dtype}")
    # >= 1 row per profile holds by construction once the frame is non-empty; kept explicit for the contract.
    if df.groupby("profile_id").size().min() < 1:
        raise SchemaError("a profile has no rows")


def prepare(raw_csv: Path, out_parquet: Path) -> Path:
    """Load, validate, add `t` (s, restarting at 0 per profile), sort by (profile_id, t), write parquet."""
    df = load_raw(raw_csv)
    validate(df)
    # Rows are in recording order within a profile, so t follows file order (not a value sort).
    df["t"] = df.groupby("profile_id").cumcount() * SAMPLE_PERIOD_S
    df = df.sort_values(["profile_id", "t"], kind="stable").reset_index(drop=True)
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_parquet, index=False)
    return out_parquet
