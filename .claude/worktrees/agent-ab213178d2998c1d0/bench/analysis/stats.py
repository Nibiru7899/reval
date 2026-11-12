"""Statistics (docs/06 section 6): stratified cluster bootstrap, non-inferiority, Holm, intersection-union.

Strata (change type) are a fixed design factor: clusters (base snapshots) are resampled with replacement
*within* each stratum, so every resample keeps the design count of clusters per stratum and strata are
never mixed. Ratio metrics are recomputed from pooled sums in each resample. Everything is deterministic
given ``seed``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from bench.analysis.metrics import Metric, prepare

Combine = Callable[..., float]


def _cluster_arrays(
    df: pd.DataFrame, metrics: Sequence[Metric], strata: str, cluster: str
) -> list[tuple[list[np.ndarray], list[np.ndarray]]]:
    """Per stratum (sorted): per-metric per-cluster (num, den) sums, aligned across metrics."""
    keys = df[[strata, cluster]].drop_duplicates().sort_values([strata, cluster])
    per_metric = []
    for m in metrics:
        p = m.parts(df)
        j = p.join(df[[strata, cluster]], how="left")
        per_metric.append(j.groupby([strata, cluster])[["num", "den"]].sum())
    out = []
    for _, grp in keys.groupby(strata, sort=True):
        idx = pd.MultiIndex.from_frame(grp[[strata, cluster]])
        nums, dens = [], []
        for agg in per_metric:
            a = agg.reindex(idx, fill_value=0.0)
            nums.append(a["num"].to_numpy(float))
            dens.append(a["den"].to_numpy(float))
        out.append((nums, dens))
    return out


def _value(num: np.ndarray, den: np.ndarray, offset: float) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den == 0.0, np.nan, num / np.where(den == 0.0, 1.0, den)) - offset


def bootstrap_samples(
    df: pd.DataFrame,
    metrics: Sequence[Metric],
    combine: Combine,
    *,
    strata: str = "change_type",
    cluster: str = "base_snapshot",
    n: int = 10_000,
    seed: int = 0,
) -> tuple[float, np.ndarray]:
    """Point estimate and ``n`` bootstrap replicates of ``combine(*metric_values)``.

    All metrics share the same cluster draws (paired). ``combine`` must be vectorised over numpy arrays.
    """
    if df.empty:
        return math.nan, np.full(n, np.nan)
    df = df.reset_index(drop=True)
    tables = _cluster_arrays(df, metrics, strata, cluster)
    tot_n = [np.zeros(n) for _ in metrics]
    tot_d = [np.zeros(n) for _ in metrics]
    est_n = [0.0] * len(metrics)
    est_d = [0.0] * len(metrics)
    rng = np.random.default_rng(seed)
    for nums, dens in tables:  # sorted strata: stable draw order
        k = len(nums[0])
        draw = rng.integers(0, k, size=(n, k))
        for i in range(len(metrics)):
            tot_n[i] += nums[i][draw].sum(axis=1)
            tot_d[i] += dens[i][draw].sum(axis=1)
            est_n[i] += float(nums[i].sum())
            est_d[i] += float(dens[i].sum())
    est_vals = [
        float(_value(np.array(est_n[i]), np.array(est_d[i]), m.offset)) for i, m in enumerate(metrics)
    ]
    samples = [_value(tot_n[i], tot_d[i], m.offset) for i, m in enumerate(metrics)]
    return float(combine(*est_vals)), np.asarray(combine(*samples), dtype=float)


def percentile_interval(samples: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    """Two-sided ``1 - alpha`` percentile interval; ``nan`` replicates (zero denominator) are ignored."""
    s = samples[~np.isnan(samples)]
    if s.size == 0:
        return math.nan, math.nan
    lo, hi = np.percentile(s, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def stratified_cluster_bootstrap(
    df: pd.DataFrame,
    metric_fn: Callable[[pd.DataFrame], float],
    *,
    strata: str = "change_type",
    cluster: str = "base_snapshot",
    n: int = 10_000,
    seed: int = 0,
) -> tuple[float, float, float]:
    """(estimate, lo, hi): 95 % percentile CI of ``metric_fn`` under the stratified cluster bootstrap.

    A ``bench.analysis.metrics.Metric`` takes the fast pooled-sums path; any other callable is evaluated
    on the concatenated resampled frame (slower, same resampling).
    """
    if isinstance(metric_fn, Metric):
        est, samples = bootstrap_samples(
            df, [metric_fn], lambda x: x, strata=strata, cluster=cluster, n=n, seed=seed
        )
    else:
        est, samples = _generic(df, metric_fn, strata, cluster, n, seed)
    lo, hi = percentile_interval(samples)
    return est, lo, hi


def _generic(
    df: pd.DataFrame, fn: Callable[[pd.DataFrame], float], strata: str, cluster: str, n: int, seed: int
) -> tuple[float, np.ndarray]:
    groups = {(s, c): g for (s, c), g in df.groupby([strata, cluster], sort=True)}
    by_stratum: dict[object, list[object]] = {}
    for s, c in groups:
        by_stratum.setdefault(s, []).append(c)
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for r in range(n):
        parts = []
        for s in sorted(by_stratum, key=str):
            cl = by_stratum[s]
            for i in rng.integers(0, len(cl), size=len(cl)):
                parts.append(groups[(s, cl[int(i)])])
        out[r] = fn(pd.concat(parts, ignore_index=True))
    return float(fn(df)), out


def paired_difference_ci(
    df: pd.DataFrame,
    metric: Callable[[str], Metric],
    method_a: str,
    method_b: str,
    *,
    strata: str = "change_type",
    cluster: str = "base_snapshot",
    n: int = 10_000,
    seed: int = 0,
) -> tuple[float, float, float]:
    """(estimate, lo, hi) of ``metric(method_a) - metric(method_b)`` on the same cluster draws."""
    est, samples = bootstrap_samples(
        df,
        [metric(method_a), metric(method_b)],
        lambda a, b: a - b,
        strata=strata,
        cluster=cluster,
        n=n,
        seed=seed,
    )
    lo, hi = percentile_interval(samples)
    return est, lo, hi


def one_sided_bound(samples: np.ndarray, side: str, level: float = 0.975) -> float:
    """One-sided ``level`` bound: ``side="upper"`` is the 97.5 % quantile, ``"lower"`` the 2.5 % quantile."""
    s = samples[~np.isnan(samples)]
    if s.size == 0:
        return math.nan
    return float(np.quantile(s, level if side == "upper" else 1.0 - level))


def bootstrap_p(samples: np.ndarray, null: float, alternative: str) -> float:
    """One-sided bootstrap p-value of H0 on the replicates.

    ``alternative="less"`` tests stat < null (p = share of replicates >= null); ``"greater"`` tests
    stat >= null (p = share of replicates < null). Add-one smoothing, so p >= 1/(n+1).
    """
    s = samples[~np.isnan(samples)]
    if s.size == 0:
        return 1.0
    bad = np.sum(s >= null) if alternative == "less" else np.sum(s < null)
    return float((bad + 1) / (s.size + 1))


def non_inferior(upper_bound: float, delta: float) -> bool:
    """Non-inferiority: the one-sided 97.5 % upper bound must be strictly below ``delta``."""
    return bool(upper_bound < delta)  # nan compares False: undefined never passes (fail closed)


def holm(pvalues: Mapping[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm-Bonferroni step-down: ``{hypothesis: rejected}``. Ties are ordered by name for determinism."""
    order = sorted(pvalues, key=lambda k: (pvalues[k], k))
    m = len(order)
    out = dict.fromkeys(pvalues, False)
    for rank, k in enumerate(order):
        if pvalues[k] <= alpha / (m - rank):
            out[k] = True
        else:
            break  # once one fails, all larger p-values fail too
    return out


def intersection_union(parts: Mapping[str, bool]) -> bool:
    """H1 holds only if every component holds (an empty set of components does not hold)."""
    return bool(parts) and all(parts.values())


def filter_frame(
    df: pd.DataFrame, *, tier: str | None = None, exclude_change_types: Sequence[str] = ()
) -> pd.DataFrame:
    """Select a tier and/or drop change types (for example Tier B without T9 for H2)."""
    out = df if tier is None else df[df["tier"] == tier]
    return out[~out["change_type"].isin(list(exclude_change_types))]


__all__ = [
    "bootstrap_p",
    "bootstrap_samples",
    "filter_frame",
    "holm",
    "intersection_union",
    "non_inferior",
    "one_sided_bound",
    "paired_difference_ci",
    "percentile_interval",
    "prepare",
    "stratified_cluster_bootstrap",
]
