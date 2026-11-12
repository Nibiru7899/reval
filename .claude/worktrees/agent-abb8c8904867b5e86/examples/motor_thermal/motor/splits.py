"""Profile-level splits (docs/05 section 2). Never split by rows (AGENTS rule 6)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml

SplitName = Literal["train", "calib", "test", "reserve"]
_NAMES = ("train", "calib", "test", "reserve")


@dataclass(frozen=True)
class Splits:
    """Disjoint sets of profile ids."""

    train: tuple[int, ...]
    calib: tuple[int, ...]
    test: tuple[int, ...]
    reserve: tuple[int, ...]

    def of(self, profile_id: int) -> str:
        """Name of the split containing ``profile_id``; KeyError if it is in none."""
        for name in _NAMES:
            if profile_id in getattr(self, name):
                return name
        raise KeyError(f"profile {profile_id} is in no split")


def _check_disjoint(s: Splits) -> None:
    seen: set[int] = set()
    for name in _NAMES:
        members = getattr(s, name)
        ids = set(members)
        if len(ids) != len(members):
            raise ValueError(f"duplicate profile ids in {name}")
        if seen & ids:
            raise ValueError(f"splits are not disjoint: {sorted(seen & ids)} reappear in {name}")
        seen |= ids


def _length(summary: pd.DataFrame) -> pd.Series:
    col = "n_rows" if "n_rows" in summary.columns else "duration_h"
    return summary.set_index("profile_id")[col]


def make_splits(
    summary: pd.DataFrame,
    seed: int,
    test_ids: Sequence[int] | None,
    fractions: tuple[float, float, float] = (0.65, 0.15, 0.20),
    n_reserve: int = 3,
) -> Splits:
    """Deterministic profile-level split.

    ``test`` = ``test_ids`` plus random extra profiles (stratified over length) up to the test
    fraction. The rest is sorted by length and dealt evenly into train and calib so both span
    short and long profiles; ``reserve`` is then drawn from train-like profiles.
    """
    length = _length(summary)
    n = len(length)
    published = [int(i) for i in (test_ids or ())]
    unknown = sorted(set(published) - {int(i) for i in length.index})
    if unknown:
        raise ValueError(f"test_ids not in the data: {unknown}")
    rng = np.random.default_rng(seed)

    n_test = max(round(fractions[2] * n), len(published))
    n_calib = round(fractions[1] * n)

    pool = sorted(
        (int(i) for i in length.index if int(i) not in published),
        key=lambda i: (length[i], i),
    )
    # Extras for test: one random pick per equal-sized length stratum.
    n_extra = n_test - len(published)
    extras: list[int] = []
    if n_extra > 0:
        for chunk in np.array_split(np.array(pool), n_extra):
            extras.append(int(rng.choice(chunk)))
    test = tuple(sorted({*published, *extras}))

    rest = [i for i in pool if i not in extras]
    m = len(rest)
    calib: list[int] = []
    train: list[int] = []
    for k, pid in enumerate(rest):
        # Error-diffusion deal: spreads calib evenly over the length-sorted list.
        if (k + 1) * n_calib // m > k * n_calib // m:
            calib.append(pid)
        else:
            train.append(pid)
    reserve = sorted(int(x) for x in rng.choice(np.array(train), size=n_reserve, replace=False))
    train = [i for i in train if i not in reserve]

    out = Splits(
        train=tuple(sorted(train)),
        calib=tuple(sorted(calib)),
        test=test,
        reserve=tuple(reserve),
    )
    _check_disjoint(out)
    return out


def save_splits(
    splits: Splits,
    path: Path,
    *,
    seed: int,
    source_note: str,
    published_test_ids: Sequence[int] = (),
) -> None:
    """Write the splits file (keys train, calib, test, reserve, seed, source_note)."""
    doc: dict[str, Any] = {
        "train": list(splits.train),
        "calib": list(splits.calib),
        "test": list(splits.test),
        "reserve": list(splits.reserve),
        "published_test_ids": [int(i) for i in published_test_ids],
        "seed": seed,
        "source_note": source_note,
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False, width=100), encoding="utf-8")


def load_splits(path: Path) -> Splits:
    """Read a splits file and assert pairwise disjointness."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    s = Splits(
        train=tuple(int(i) for i in doc["train"]),
        calib=tuple(int(i) for i in doc["calib"]),
        test=tuple(int(i) for i in doc["test"]),
        reserve=tuple(int(i) for i in doc["reserve"]),
    )
    _check_disjoint(s)
    return s


def split_frame(df: pd.DataFrame, splits: Splits, name: SplitName) -> pd.DataFrame:
    """Rows of ``df`` whose profile belongs to split ``name``."""
    return df[df["profile_id"].isin(getattr(splits, name))]
