import numpy as np
import pandas as pd
import pytest
from motor.splits import Splits, load_splits, make_splits, save_splits, split_frame


def _summary(n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    return pd.DataFrame({"profile_id": range(1, n + 1), "n_rows": rng.integers(1000, 50000, n)})


def test_disjoint_and_cover():
    s = make_splits(_summary(), seed=0, test_ids=(5, 7))
    allids = [*s.train, *s.calib, *s.test, *s.reserve]
    assert sorted(allids) == list(range(1, 41))
    assert len(set(allids)) == 40
    assert len(s.reserve) == 3
    assert len(s.test) == 8


def test_same_seed_same_splits_and_other_seed_differs():
    a = make_splits(_summary(), seed=0, test_ids=(5, 7))
    assert a == make_splits(_summary(), seed=0, test_ids=(5, 7))
    assert a != make_splits(_summary(), seed=1, test_ids=(5, 7))


def test_test_ids_subset():
    s = make_splits(_summary(), seed=3, test_ids=(5, 7))
    assert {5, 7} <= set(s.test)


def test_unknown_test_id_rejected():
    with pytest.raises(ValueError):
        make_splits(_summary(), seed=0, test_ids=(999,))


def test_split_frame_only_requested(synthetic_measures):
    df = synthetic_measures(n_profiles=4, n_rows=20)
    ids = sorted(df["profile_id"].unique())
    s = Splits(train=(ids[0], ids[1]), calib=(ids[2],), test=(ids[3],), reserve=())
    assert set(split_frame(df, s, "train")["profile_id"]) == {ids[0], ids[1]}
    assert set(split_frame(df, s, "test")["profile_id"]) == {ids[3]}
    assert s.of(ids[2]) == "calib"


def test_roundtrip_and_disjoint_check(tmp_path):
    s = make_splits(_summary(), seed=0, test_ids=(5,))
    p = tmp_path / "s.yaml"
    save_splits(s, p, seed=0, source_note="n", published_test_ids=(5,))
    assert load_splits(p) == s
    p.write_text(
        "train: [1, 2]\ncalib: [2]\ntest: [3]\nreserve: []\nseed: 0\nsource_note: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_splits(p)
