import math

import numpy as np
import pytest

from reval.uq.conformal import GroupedSplitConformal, conformal_quantile


def test_per_group_quantiles_match_conformal_quantile() -> None:
    rng = np.random.default_rng(0)
    yt = rng.normal(size=300)
    yp = yt + rng.normal(size=300)
    groups = ["a"] * 100 + ["b"] * 150 + ["c"] * 50
    g = GroupedSplitConformal(0.1).fit(yt, yp, groups)
    arr = np.asarray(groups)
    for name in "abc":
        m = arr == name
        assert g.q_by_group[name] == conformal_quantile(np.abs(yt[m] - yp[m]), 0.1)
    lo, hi = g.interval(5.0, "a")  # type: ignore[misc]
    assert hi - 5.0 == pytest.approx(g.q_by_group["a"])
    assert 5.0 - lo == pytest.approx(g.q_by_group["a"])


def test_unknown_group_raises() -> None:
    g = GroupedSplitConformal(0.1).fit(np.zeros(20), np.ones(20), ["a"] * 20)
    with pytest.raises(KeyError):
        g.interval(0.0, "zzz")


def test_too_few_scores_gives_none() -> None:
    g = GroupedSplitConformal(0.1).fit(np.zeros(25), np.ones(25), ["big"] * 20 + ["tiny"] * 5)
    assert math.isinf(g.q_by_group["tiny"])
    assert g.interval(1.0, "tiny") is None
    assert g.interval(1.0, "big") is not None


def test_length_mismatch_and_alpha() -> None:
    with pytest.raises(ValueError):
        GroupedSplitConformal(0.1).fit(np.zeros(3), np.zeros(3), ["a"])
    with pytest.raises(ValueError):
        GroupedSplitConformal(1.5)
