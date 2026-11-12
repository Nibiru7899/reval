"""Benchmark metrics (docs/06 section 3), all as **ratios of sums** over a tidy per-claim frame.

A ``Metric`` exposes row-level ``(num, den)`` parts so the bootstrap can pool them per resample
(``bench.analysis.stats``). A zero denominator is never averaged: pooled sums with ``den == 0`` give
``nan`` as the final value only. WAIVED rows are dropped. Tiers are never pooled: a frame with more
than one tier is rejected.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from bench.metrics.records import DECIDED

_GROUP = ["scenario_id", "method"]
_SCENARIO_COLS = ["cost", "b0_cost", "false_alarm_cost", "n_bench_runs", "ilp_cost", "greedy_cost"]
Parts = tuple[pd.Series, pd.Series]  # (num, den), aligned to the cleaned frame's index


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Drop WAIVED rows, enforce a single tier and consistent scenario-level columns."""
    out = df[(df["status_after"] != "waived") & (df["status_before"] != "waived")]
    if out["tier"].nunique() > 1:
        raise ValueError("Tier A and Tier B must never be pooled; filter on `tier` first")
    if len(out):
        spread = out.groupby(_GROUP)[_SCENARIO_COLS].nunique(dropna=False).max()
        if (spread > 1).any():
            raise ValueError(
                f"scenario-level columns differ within a (scenario, method): {dict(spread[spread > 1])}"
            )
    return out


def _first(df: pd.DataFrame) -> pd.Series:
    """True on the first claim row of every (scenario, method): scenario-level values are counted there."""
    return ~df.duplicated(_GROUP)


def _f(mask: pd.Series) -> pd.Series:
    return mask.astype(float)


def _known(df: pd.DataFrame) -> pd.Series:
    return df["truth_violated"].notna()


def _bad(df: pd.DataFrame) -> pd.Series:
    return df["accepted"].astype(bool) & df["truth_violated"].fillna(False).astype(bool)


def _flag(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].fillna(False).astype(bool)


@dataclass(frozen=True)
class Metric:
    """``value = sum(num) / sum(den) - offset`` over the rows of ``method`` (``nan`` if ``sum(den) == 0``)."""

    name: str
    method: str
    fn: Callable[[pd.DataFrame], Parts]
    offset: float = 0.0
    needs_all_methods: bool = False  # paired metrics look at a second method too

    def parts(self, df: pd.DataFrame) -> pd.DataFrame:
        """Row-level ``num``/``den`` (indexed like ``df``); only rows that matter are present."""
        clean = prepare(df)
        view = clean if self.needs_all_methods else clean[clean["method"] == self.method]
        num, den = self.fn(view)
        return pd.DataFrame({"num": num.astype(float), "den": den.astype(float)})

    def __call__(self, df: pd.DataFrame) -> float:
        p = self.parts(df)
        d = float(p["den"].sum())
        return math.nan if d == 0.0 else float(p["num"].sum()) / d - self.offset


def _ratio(
    num: Callable[[pd.DataFrame], pd.Series], den: Callable[[pd.DataFrame], pd.Series]
) -> Callable[[pd.DataFrame], Parts]:
    return lambda df: (_f(num(df)), _f(den(df)))


def _once(df: pd.DataFrame, col: str) -> pd.Series:
    return df[col].astype(float).where(_first(df), 0.0)


# --- impact analysis (RQ1) --------------------------------------------------------------------------


def _tp(d: pd.DataFrame) -> pd.Series:
    return d["truly_affected"].astype(bool) & d["predicted_affected"].astype(bool)


def impact_recall(method: str) -> Metric:
    """TP / truly affected."""
    return Metric("impact_recall", method, _ratio(_tp, lambda d: d["truly_affected"].astype(bool)))


def impact_precision(method: str) -> Metric:
    """TP / predicted affected."""
    return Metric("impact_precision", method, _ratio(_tp, lambda d: d["predicted_affected"].astype(bool)))


def impact_f2(method: str) -> Metric:
    """F2 = 5 TP / (4 * truly affected + predicted affected): a ratio of sums (FN = T - TP, FP = P - TP)."""

    def fn(d: pd.DataFrame) -> Parts:
        return 5.0 * _f(_tp(d)), 4.0 * _f(d["truly_affected"].astype(bool)) + _f(
            d["predicted_affected"].astype(bool)
        )

    return Metric("impact_f2", method, fn)


# --- unsafe acceptance ------------------------------------------------------------------------------


def uar_evidence(method: str) -> Metric:
    """|accepted and not accepted by B0| / |accepted|."""
    acc = lambda d: d["accepted"].astype(bool)  # noqa: E731
    return Metric("uar_evidence", method, _ratio(lambda d: acc(d) & ~d["b0_accepted"].astype(bool), acc))


def uar_truth(method: str) -> Metric:
    """|accepted and requirement actually violated| / |accepted with known truth|."""
    return Metric("uar_truth", method, _ratio(_bad, lambda d: d["accepted"].astype(bool) & _known(d)))


def uar_star(method: str) -> Metric:
    """Per-claim risk: |accepted and violated| / |claims with known truth|; not gameable by accepting less."""
    return Metric("uar_star", method, _ratio(_bad, _known))


def decision_coverage(method: str) -> Metric:
    """Share of claims in a decided status (SUPPORTED or VIOLATED) after the plan."""
    return Metric(
        "decision_coverage",
        method,
        lambda d: (_f(d["status_after"].isin(DECIDED)), pd.Series(1.0, index=d.index)),
    )


# --- cost -------------------------------------------------------------------------------------------


def cost_ratio(method: str) -> Metric:
    """sum(plan cost) / sum(B0 cost), scenario-level values counted once per scenario."""
    return Metric("cost_ratio", method, lambda d: (_once(d, "cost"), _once(d, "b0_cost")))


def mean_cost(method: str) -> Metric:
    """Absolute plan cost per scenario."""
    return Metric("mean_cost", method, lambda d: (_once(d, "cost"), _f(_first(d))))


def mean_bench_runs(method: str) -> Metric:
    """Number of bench (measurement-fidelity) runs per scenario, from ``n_bench_runs``."""
    return Metric("mean_bench_runs", method, lambda d: (_once(d, "n_bench_runs"), _f(_first(d))))


def cost_per_decided(method: str) -> Metric:
    """sum(cost) / number of decided claims (coverage differs between methods)."""
    return Metric(
        "cost_per_decided", method, lambda d: (_once(d, "cost"), _f(d["status_after"].isin(DECIDED)))
    )


def false_alarm_cost(method: str) -> Metric:
    """Cost spent on runs whose evidence moved < epsilon, per scenario."""
    return Metric("false_alarm_cost", method, lambda d: (_once(d, "false_alarm_cost"), _f(_first(d))))


def false_alarm_share(method: str) -> Metric:
    """False-alarm cost as a share of the method's total cost."""
    return Metric("false_alarm_share", method, lambda d: (_once(d, "false_alarm_cost"), _once(d, "cost")))


def log_cost_ratio(method: str, reference: str = "B1") -> Metric:
    """Paired mean of log(C_method / C_reference) over scenarios present under both methods.

    Scenarios where either cost is <= 0 have no defined log ratio and are excluded (den 0); count them
    with ``n_log_ratio_excluded``.
    """

    def fn(d: pd.DataFrame) -> Parts:
        first = d[_first(d)]
        ref = first[first["method"] == reference].set_index("scenario_id")["cost"]
        rows = first[first["method"] == method]
        ca = rows["cost"].astype(float)
        cr = rows["scenario_id"].map(ref).astype(float)
        ok = (ca > 0) & (cr > 0)
        num = pd.Series(np.log(ca.where(ok, 1.0) / cr.where(ok, 1.0)), index=rows.index)
        return num, _f(ok)

    return Metric(f"log_cost_ratio_vs_{reference}", method, fn, needs_all_methods=True)


def n_log_ratio_excluded(df: pd.DataFrame, method: str, reference: str = "B1") -> int:
    """Scenarios of ``method`` without a defined paired log ratio (missing reference or a zero cost)."""
    p = log_cost_ratio(method, reference).parts(df)
    clean = prepare(df)
    n_scen = clean.loc[clean["method"] == method, "scenario_id"].nunique()
    return int(n_scen - p["den"].sum())


# --- reproducibility and planner --------------------------------------------------------------------


def reproducibility(method: str) -> Metric:
    """Share of re-executed assessments identical in input_hash and status (rows with ``None`` skipped)."""
    return Metric(
        "reproducibility",
        method,
        _ratio(lambda d: _flag(d, "reproducible"), lambda d: d["reproducible"].notna()),
    )


def optimality_gap(method: str = "reval") -> Metric:
    """sum(greedy cost) / sum(ILP cost) - 1 over scenarios with both costs recorded."""

    def fn(d: pd.DataFrame) -> Parts:
        ok = d["ilp_cost"].notna() & d["greedy_cost"].notna() & _first(d)
        return d["greedy_cost"].astype(float).where(ok, 0.0), d["ilp_cost"].astype(float).where(ok, 0.0)

    return Metric("optimality_gap", method, fn, offset=1.0)


FACTORIES: dict[str, Callable[[str], Metric]] = {
    f.__name__: f
    for f in (
        impact_recall, impact_precision, impact_f2, uar_evidence, uar_truth, uar_star, decision_coverage,
        cost_ratio, mean_cost, mean_bench_runs, cost_per_decided, false_alarm_cost, false_alarm_share,
        reproducibility, optimality_gap,
    )
}  # fmt: skip


def compute_all(df: pd.DataFrame, method: str) -> dict[str, float]:
    """Every single-method metric for ``method`` (``nan`` where undefined)."""
    return {name: f(method)(df) for name, f in FACTORIES.items()}
