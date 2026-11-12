"""P5-12: stratified cluster bootstrap, non-inferiority, Holm."""

import math

import numpy as np
import pandas as pd
import pytest

from bench.analysis import metrics as M
from bench.analysis import stats as T
from bench.metrics.records import ClaimRecord, to_frame


def rec(
    scen: str, cluster: str, ctype: str, bad: bool, method: str = "reval", cost: float = 1.0
) -> ClaimRecord:
    return ClaimRecord(
        scenario_id=scen, change_type=ctype, tier="A", base_snapshot=cluster, method=method, claim_id="c",
        status_before="supported", status_after="supported", accepted=True, b0_accepted=True,
        truly_affected=False, predicted_affected=False, truth_violated=bad, cost=cost, b0_cost=2.0,
    )  # fmt: skip


def bernoulli_frame(n_clusters: int = 200, n_bad: int = 60, ctype: str = "T1") -> pd.DataFrame:
    return to_frame([rec(f"s{i}", f"b{i}", ctype, i < n_bad) for i in range(n_clusters)])


def test_known_ci_matches_normal_approximation() -> None:
    est, lo, hi = T.stratified_cluster_bootstrap(bernoulli_frame(), M.uar_truth("reval"), n=4000, seed=1)
    se = math.sqrt(0.3 * 0.7 / 200)
    assert est == pytest.approx(0.3)
    assert lo == pytest.approx(0.3 - 1.96 * se, abs=0.01)
    assert hi == pytest.approx(0.3 + 1.96 * se, abs=0.01)


def test_deterministic_given_seed_and_different_across_seeds() -> None:
    df, m = bernoulli_frame(40, 12), M.uar_truth("reval")
    a = T.bootstrap_samples(df, [m], lambda x: x, n=500, seed=7)
    b = T.bootstrap_samples(df, [m], lambda x: x, n=500, seed=7)
    c = T.bootstrap_samples(df, [m], lambda x: x, n=500, seed=8)
    assert a[0] == b[0] and np.array_equal(a[1], b[1])
    assert not np.array_equal(a[1], c[1])
    assert T.stratified_cluster_bootstrap(df, m, n=500, seed=7) == T.stratified_cluster_bootstrap(
        df, m, n=500, seed=7
    )


def test_strata_are_never_mixed() -> None:
    # T1: all safe, T2: all unsafe, 5 clusters each. Resampling inside strata keeps the pooled share at
    # exactly 0.5 in every replicate; resampling across strata would spread it out.
    rows = [rec(f"a{i}", f"b{i}", "T1", False) for i in range(5)]
    rows += [rec(f"c{i}", f"b{i}", "T2", True) for i in range(5)]
    est, lo, hi = T.stratified_cluster_bootstrap(to_frame(rows), M.uar_truth("reval"), n=300, seed=3)
    assert (est, lo, hi) == (0.5, 0.5, 0.5)


def test_same_cluster_id_in_two_strata_is_two_clusters() -> None:
    rows = [rec("a", "b0", "T1", False), rec("c", "b0", "T2", True), rec("d", "b1", "T2", True)]
    _, samples = T.bootstrap_samples(to_frame(rows), [M.uar_truth("reval")], lambda x: x, n=200, seed=0)
    assert set(np.unique(samples)) <= {1 / 3, 2 / 3, 1.0}
    assert samples.max() == pytest.approx(2 / 3)  # the T1 cluster (safe) is resampled into every replicate


def test_slow_generic_path_agrees_with_fast_path() -> None:
    df = bernoulli_frame(20, 6)
    m = M.uar_truth("reval")
    fast = T.stratified_cluster_bootstrap(df, m, n=300, seed=5)
    slow = T.stratified_cluster_bootstrap(df, lambda d: m(d), n=300, seed=5)
    assert fast[0] == slow[0]
    assert fast[1:] == pytest.approx(slow[1:], abs=0.08)  # different RNG consumption, same distribution


def test_paired_difference_uses_shared_draws() -> None:
    rows = [rec(f"s{i}", f"b{i}", "T1", i < 6) for i in range(20)]
    rows += [rec(f"s{i}", f"b{i}", "T1", i < 6, method="B0") for i in range(20)]
    est, lo, hi = T.paired_difference_ci(to_frame(rows), M.uar_truth, "reval", "B0", n=300, seed=2)
    assert (est, lo, hi) == (0.0, 0.0, 0.0)  # identical data: pairing cancels all resampling noise


def test_paired_difference_detects_gap() -> None:
    rows = [rec(f"s{i}", f"b{i}", "T1", False) for i in range(30)]
    rows += [rec(f"s{i}", f"b{i}", "T1", i % 2 == 0, method="B3") for i in range(30)]
    est, lo, hi = T.paired_difference_ci(to_frame(rows), M.uar_truth, "B3", "reval", n=500, seed=2)
    assert est == pytest.approx(0.5) and 0.3 < lo < hi < 0.7
    assert not T.non_inferior(hi, 0.05)


def test_log_cost_ratio_bootstrap() -> None:
    rows = []
    for i in range(10):
        rows += [
            rec(f"s{i}", f"b{i}", "T1", False, cost=10),
            rec(f"s{i}", f"b{i}", "T1", False, "B1", cost=100),
        ]
    est, _, hi = T.stratified_cluster_bootstrap(to_frame(rows), M.log_cost_ratio("reval"), n=200, seed=0)
    assert est == pytest.approx(math.log(0.1)) and hi < 0


def test_zero_accept_clusters_do_not_become_nan_average() -> None:
    rows = [rec("s0", "b0", "T1", True), rec("s1", "b1", "T1", False)]
    for i in (2, 3):
        rows.append(
            ClaimRecord(
                f"s{i}", "T1", "A", f"b{i}", "reval", "c", "supported", "stale",
                False, True, False, False, None, 1.0, 2.0,
            )
        )  # fmt: skip
    est, lo, hi = T.stratified_cluster_bootstrap(to_frame(rows), M.uar_truth("reval"), n=400, seed=0)
    assert est == pytest.approx(0.5)
    assert 0.0 <= lo <= hi <= 1.0  # replicates with no accepted claim are undefined and dropped, not averaged


def test_non_inferior_strict_and_nan_fails_closed() -> None:
    assert T.non_inferior(0.01, 0.02)
    assert not T.non_inferior(0.02, 0.02)
    assert not T.non_inferior(math.nan, 0.02)


def test_one_sided_bounds_and_p() -> None:
    s = np.arange(1, 1001) / 1000.0
    assert T.one_sided_bound(s, "upper") == pytest.approx(0.975, abs=0.002)
    assert T.one_sided_bound(s, "lower") == pytest.approx(0.025, abs=0.002)
    assert T.bootstrap_p(s, 0.0005, "less") == 1.0  # every replicate is >= the null
    assert T.bootstrap_p(s, 2.0, "less") == pytest.approx(1 / 1001)
    assert T.bootstrap_p(s, 0.0, "greater") == pytest.approx(1 / 1001)


def test_holm_hand_examples() -> None:
    # m=3: thresholds 0.05/3, 0.05/2, 0.05. Smallest p .01 passes (<= .0167); next .03 > .025 stops the chain.
    assert T.holm({"H2a": 0.01, "H2b": 0.04, "H3": 0.03}) == {"H2a": True, "H2b": False, "H3": False}
    assert T.holm({"a": 0.001, "b": 0.02, "c": 0.04}) == {"a": True, "b": True, "c": True}
    assert T.holm({"a": 0.2, "b": 0.001}) == {"a": False, "b": True}
    assert T.holm({"a": 0.03, "b": 0.03}) == {"a": False, "b": False}  # 0.03 > 0.025


def test_intersection_union() -> None:
    assert T.intersection_union({"a": True, "b": True})
    assert not T.intersection_union({"a": True, "b": False})
    assert not T.intersection_union({})


def test_filter_frame_tier_b_without_t9() -> None:
    df = to_frame([rec("s0", "b0", "T9", False), rec("s1", "b1", "T7", False)])
    assert set(T.filter_frame(df, exclude_change_types=["T9"])["change_type"]) == {"T7"}
