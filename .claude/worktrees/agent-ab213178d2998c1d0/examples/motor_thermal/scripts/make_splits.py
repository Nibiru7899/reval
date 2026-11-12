"""Generate the committed examples/motor_thermal/splits.yaml from the prepared parquet."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from motor.eda import profile_summary  # noqa: E402
from motor.splits import make_splits, save_splits  # noqa: E402

SEED = 0
# Validation profile 58 stays in calib (not test); test profiles are 65 and 72.
PUBLISHED_TEST_IDS = (65, 72)
SOURCE_NOTE = (
    "Published generalization profiles of the Kirchgaessner et al. line of work: validation "
    "profile 58, test profiles 65 and 72, as cited in arXiv:2511.16093 (citing the original "
    "spec). VERIFY against the upb-lea code before relying on these ids. Profile 58 is kept in "
    "calib. Extra test profiles are drawn with the seed to reach ~20 percent of profiles."
)


def main() -> None:
    df = pd.read_parquet(ROOT / "data" / "processed" / "measures.parquet")
    summary = profile_summary(df)
    splits = make_splits(summary, seed=SEED, test_ids=PUBLISHED_TEST_IDS)
    save_splits(
        splits,
        ROOT / "splits.yaml",
        seed=SEED,
        source_note=SOURCE_NOTE,
        published_test_ids=PUBLISHED_TEST_IDS,
    )
    dur = summary.set_index("profile_id")["duration_h"]
    for name in ("train", "calib", "test", "reserve"):
        ids = getattr(splits, name)
        print(f"{name}: {len(ids)} profiles, {dur.loc[list(ids)].sum():.1f} h")
    print(f"profile 58 is in: {splits.of(58)}")


if __name__ == "__main__":
    main()
