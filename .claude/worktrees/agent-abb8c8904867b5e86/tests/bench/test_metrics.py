"""P5-10: metrics on synthetic records with hand-computed answers."""

import math

import pytest

from bench.analysis import metrics as M
from bench.metrics.records import ClaimRecord, to_frame

S, V, ST = "supported", "violated", "stale"


def rec(i: int, scen: str = "s1", method: str = "reval", **kw: object) -> ClaimRecord:
    base: dict[str, object] = {
        "scenario_id": scen, "change_type": "T1", "tier": "A", "base_snapshot": "b1", "method": method,
        "claim_id": f"c{i}", "status_before": S, "status_after": S, "accepted": True, "b0_accepted": True,
        "truly_affected": False, "predicted_affected": False, "truth_violated": False, "cost": 10.0,
        "b0_cost": 100.0,
    }  # fmt: skip
    base.update(kw)
    return ClaimRecord(**base)  # type: ignore[arg-type]


def test_impact_recall_precision_f2() -> None:
    # truly affected: c0-c3 (4); predicted: c0,c1,c2,c4,c5 (5); TP = c0,c1,c2 = 3
    rows = [rec(i, truly_affected=i < 4, predicted_affected=i in (0, 1, 2, 4, 5)) for i in range(8)]
    df = to_frame(rows)
    assert M.impact_recall("reval")(df) == pytest.approx(3 / 4)
    assert M.impact_precision("reval")(df) == pytest.approx(3 / 5)
    assert M.impact_f2("reval")(df) == pytest.approx(5 * 3 / (4 * 4 + 5))
    p, r = 3 / 5, 3 / 4
    assert M.impact_f2("reval")(df) == pytest.approx(5 * p * r / (4 * p + r))  # the usual F-beta form


def test_uar_evidence_truth_star_with_unknown_truth() -> None:
    rows = [
        rec(0, accepted=True, b0_accepted=False, truth_violated=True),  # unsafe on both oracles
        rec(1, accepted=True, b0_accepted=True, truth_violated=False),
        rec(2, accepted=True, b0_accepted=True, truth_violated=None),  # Tier A subject without truth
        rec(3, accepted=True, b0_accepted=True, truth_violated=False),
        rec(4, accepted=False, status_after=ST, b0_accepted=True, truth_violated=True),  # not accepted
        rec(5, accepted=False, status_after=ST, b0_accepted=False, truth_violated=None),
    ]
    df = to_frame(rows)
    assert M.uar_evidence("reval")(df) == pytest.approx(1 / 4)
    assert M.uar_truth("reval")(df) == pytest.approx(1 / 3)  # accepted with known truth: c0, c1, c3
    assert M.uar_star("reval")(df) == pytest.approx(1 / 4)  # known truth: c0, c1, c3, c4


def test_uar_is_ratio_of_sums_and_zero_accept_scenario_contributes_nothing() -> None:
    a = [rec(i, "s1", accepted=True, truth_violated=i == 0) for i in range(4)]  # 1 bad of 4 accepted
    b = [rec(i, "s2", accepted=True, truth_violated=i < 2) for i in range(2)]  # 2 bad of 2 accepted
    z = [
        rec(i, "s3", accepted=False, status_after=ST, truth_violated=True) for i in range(5)
    ]  # zero accepted
    df = to_frame(a + b + z)
    assert M.uar_truth("reval")(df) == pytest.approx(3 / 6)  # not mean(1/4, 1, nan), not diluted by s3
    assert M.uar_star("reval")(df) == pytest.approx(3 / 11)  # s3 claims still count among all claims
    assert math.isnan(M.uar_truth("reval")(to_frame(z)))  # all-zero accepted: 0/0 is undefined, not 0
    assert math.isnan(M.uar_evidence("reval")(to_frame(z)))
    # scenario s3 alone contributes (0, 0) to the pooled sums: adding it changes nothing
    assert M.uar_truth("reval")(to_frame(a + b)) == M.uar_truth("reval")(df)


def test_decision_coverage_excludes_waived() -> None:
    rows = [
        rec(0, status_after=S),
        rec(1, status_after=V, accepted=False),
        rec(2, status_after=ST, accepted=False),
        rec(3, status_after="inconclusive", accepted=False),
        rec(4, status_after="waived"),
    ]  # fmt: skip
    assert M.decision_coverage("reval")(to_frame(rows)) == pytest.approx(2 / 4)


def test_cost_ratio_pooled_and_counted_once_per_scenario() -> None:
    rows = [rec(i, "s1", cost=10, b0_cost=20, false_alarm_cost=4) for i in range(3)]
    rows += [rec(i, "s2", cost=30, b0_cost=100, false_alarm_cost=0) for i in range(5)]
    df = to_frame(rows)
    assert M.cost_ratio("reval")(df) == pytest.approx(40 / 120)  # mean of ratios would be 0.4
    assert M.mean_cost("reval")(df) == pytest.approx(20)
    assert M.false_alarm_cost("reval")(df) == pytest.approx(2)
    assert M.false_alarm_share("reval")(df) == pytest.approx(4 / 40)
    assert M.cost_per_decided("reval")(df) == pytest.approx(40 / 8)  # all 8 claims decided


def test_cost_per_decided_differs_by_coverage() -> None:
    rows = [rec(0, status_after=S, cost=12), rec(1, status_after=ST, accepted=False, cost=12)]
    assert M.cost_per_decided("reval")(to_frame(rows)) == pytest.approx(12)


def test_log_cost_ratio_paired_and_exclusions() -> None:
    rows = [rec(0, "s1", cost=10), rec(0, "s1", "B1", cost=100)]
    rows += [rec(0, "s2", cost=50), rec(0, "s2", "B1", cost=25)]
    rows += [rec(0, "s3", cost=0), rec(0, "s3", "B1", cost=25)]  # zero cost: log undefined, excluded
    rows += [rec(0, "s4", cost=5)]  # no B1 counterpart
    df = to_frame(rows)
    assert M.log_cost_ratio("reval")(df) == pytest.approx((math.log(0.1) + math.log(2)) / 2)
    assert M.n_log_ratio_excluded(df, "reval") == 2


def test_reproducibility_skips_unexecuted() -> None:
    rows = [
        rec(0, reproducible=True),
        rec(1, reproducible=True),
        rec(2, reproducible=False),
        rec(3, reproducible=None),
    ]
    assert M.reproducibility("reval")(to_frame(rows)) == pytest.approx(2 / 3)


def test_optimality_gap() -> None:
    rows = [rec(0, "s1", ilp_cost=10.0, greedy_cost=12.0), rec(0, "s2", ilp_cost=30.0, greedy_cost=30.0)]
    rows += [rec(0, "s3")]  # no planner costs recorded
    assert M.optimality_gap("reval")(to_frame(rows)) == pytest.approx(42 / 40 - 1)


def test_tiers_are_never_pooled() -> None:
    df = to_frame([rec(0, tier="A"), rec(1, "s2", tier="B")])
    with pytest.raises(ValueError, match="never be pooled"):
        M.uar_truth("reval")(df)


def test_scenario_level_columns_must_agree() -> None:
    df = to_frame([rec(0, cost=1), rec(1, cost=2)])
    with pytest.raises(ValueError, match="scenario-level"):
        M.cost_ratio("reval")(df)


def test_compute_all_runs_and_methods_are_separate() -> None:
    df = to_frame([rec(0), rec(0, method="B3", accepted=True, b0_accepted=False, truth_violated=True)])
    out = M.compute_all(df, "B3")
    assert out["uar_evidence"] == 1.0 and out["uar_truth"] == 1.0
    assert M.compute_all(df, "reval")["uar_truth"] == 0.0
