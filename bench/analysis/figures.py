"""Scripted figures and tables (P5-15): ``python -m bench.analysis.figures --results bench/results/<hash>``.

Reads ``rows.parquet`` (required) and optional inputs beside it; writes ``figures/*.png``, ``tables/*.tex``.
Tier A and Tier B are always separate panels. Optional inputs that are absent render as "not available":

* ``ablations/<A1..A8>[_variant]/rows.parquet``  (one bench run per ablation arm)
* ``kappa/k<value>/rows.parquet``                (A7 sweep)
* ``cost_profiles/<tag>/rows.parquet``           (P5-14; non-default ``cost_profile`` tags in main count)
* ``conformal_coverage.parquet``                 (tier, length_class, n, covered, nominal)
* ``rq4.parquet``                                (rows of ``bench.experiments.rq4``)

Colours are the Okabe-Ito colour-blind-safe set; every series also has its own marker shape and a legend,
so no series is identified by colour alone.
"""

from __future__ import annotations

import argparse
import math
import re
from collections.abc import Callable, Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from bench.analysis import metrics as M
from bench.analysis import stats as S
from bench.analysis.tables import DELTA, NA, ablation_table, h1_table, load_rows

TIERS = ("A", "B")
TIER_TITLE = {"A": "Tier A (recorded data)", "B": "Tier B (simulated world)"}
STYLE = {  # Okabe-Ito colours + distinct markers
    "reval": ("#0072B2", "o"),
    "B1": ("#E69F00", "s"),
    "B2": ("#009E73", "^"),
    "B3": ("#CC79A7", "D"),
    "B4": ("#56B4E9", "v"),
    "B0": ("#000000", "x"),
}
SERIES = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9")
MARKERS = ("o", "s", "^", "D", "v")
DPI = 130


def _natural(s: str) -> tuple[float, str]:
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return (float(m.group(1)) if m else math.inf, s)


def _panels(title: str, ylabel: str, xlabel: str = "") -> tuple[plt.Figure, list[plt.Axes]]:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True, constrained_layout=True)
    fig.suptitle(title, fontsize=11)
    for ax, t in zip(axes, TIERS, strict=True):
        ax.set_title(TIER_TITLE[t], fontsize=10)
        ax.set_xlabel(xlabel)
        ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    axes[0].set_ylabel(ylabel)
    return fig, list(axes)


def _na(ax: plt.Axes) -> None:
    ax.text(0.5, 0.5, NA, ha="center", va="center", transform=ax.transAxes, color="#555555")
    ax.set_xticks([])


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def _ci(d: pd.DataFrame, metric: M.Metric, n_boot: int) -> tuple[float, float, float]:
    """(estimate, lo, hi); NaN triple for an undefined slice."""
    try:
        return S.stratified_cluster_bootstrap(d, metric, n=n_boot, seed=0)
    except (KeyError, ValueError, IndexError):
        return math.nan, math.nan, math.nan


def _series_by_type(
    ax: plt.Axes,
    d: pd.DataFrame,
    names: Sequence[str],
    make: Callable[[str], M.Metric],
    n_boot: int,
) -> bool:
    """Dot plot with CI bars, one dot per (change type, series), series offset horizontally."""
    types = sorted(d["change_type"].unique(), key=_natural)
    drawn = False
    w = 0.7 / max(len(names), 1)
    for i, name in enumerate(names):
        xs, ys, lo, hi = [], [], [], []
        for j, ct in enumerate(types):
            est, lb, h = _ci(d[d["change_type"] == ct], make(name), n_boot)
            if math.isnan(est):
                continue
            xs.append(j + (i - (len(names) - 1) / 2) * w)
            ys.append(est)
            lo.append(est - lb if not math.isnan(lb) else 0.0)
            hi.append(h - est if not math.isnan(h) else 0.0)
        if xs:
            col, mk = STYLE.get(name, (SERIES[i % 5], MARKERS[i % 5]))
            ax.errorbar(xs, ys, yerr=[lo, hi], fmt=mk, color=col, label=name, capsize=2, ms=5, lw=1)
            drawn = True
    ax.set_xticks(range(len(types)), types)
    return drawn


def fig_cost_ratio(df: pd.DataFrame, out: Path, n_boot: int) -> None:
    """Fig. 1: plan cost / B0 cost per method and change type. Cost ratio, not UAR_truth, is the y axis;
    the UAR_truth companion is the second row."""
    methods = [m for m in ("reval", "B1", "B2", "B3", "B4") if m in set(df["method"])]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharey="row", constrained_layout=True)
    fig.suptitle("Cost ratio and UAR_truth per method and change type (95% stratified cluster bootstrap CI)")
    for r, (make, yl) in enumerate(
        ((M.cost_ratio, "plan cost / B0 cost (1)"), (M.uar_truth, "UAR_truth (1)"))
    ):
        axes[r][0].set_ylabel(yl)
        for ax, t in zip(axes[r], TIERS, strict=True):
            ax.set_title(TIER_TITLE[t], fontsize=10)
            ax.grid(axis="y", color="#dddddd", linewidth=0.6)
            d = df[df["tier"] == t]
            if d.empty or not _series_by_type(ax, d, methods, make, n_boot):
                _na(ax)
        if r == 0:
            axes[0][0].axhline(1.0, color="#888888", lw=0.8, ls="--")  # B0 = rerun all
            axes[0][1].axhline(1.0, color="#888888", lw=0.8, ls="--")
    axes[0][0].legend(title="method (dashed: B0)", fontsize=8)
    axes[1][0].set_xlabel("change type")
    axes[1][1].set_xlabel("change type")
    _save(fig, out)


def fig_impact(df: pd.DataFrame, out: Path, n_boot: int) -> None:
    """Fig. 2: ReVal impact recall, precision, F2 per change type."""
    names = ("recall", "precision", "F2")
    make = {"recall": M.impact_recall, "precision": M.impact_precision, "F2": M.impact_f2}
    fig, axes = _panels(
        "ReVal impact analysis per change type (95% CI)", "share of claims (1)", "change type"
    )
    for ax, t in zip(axes, TIERS, strict=True):
        d = df[(df["tier"] == t)]
        if d.empty:
            _na(ax)
            continue
        types = sorted(d["change_type"].unique(), key=_natural)
        w = 0.7 / 3
        for i, n in enumerate(names):
            xs, ys, lo, hi = [], [], [], []
            for j, ct in enumerate(types):
                est, lb, h = _ci(d[d["change_type"] == ct], make[n]("reval"), n_boot)
                if math.isnan(est):
                    continue
                xs.append(j + (i - 1) * w)
                ys.append(est)
                lo.append(est - lb if not math.isnan(lb) else 0.0)
                hi.append(h - est if not math.isnan(h) else 0.0)
            ax.errorbar(
                xs, ys, yerr=[lo, hi], fmt=MARKERS[i], color=SERIES[i], label=n, capsize=2, ms=5, lw=1
            )
        ax.set_xticks(range(len(types)), types)
        ax.set_ylim(-0.05, 1.05)
    axes[0].legend(fontsize=8)
    _save(fig, out)


def _sweep(
    frames: dict[str, pd.DataFrame], tier: str, make: Callable[[str], M.Metric], method: str = "reval"
) -> list[tuple[str, float]]:
    out = []
    for k in sorted(frames, key=_natural):
        d = frames[k][frames[k]["tier"] == tier]
        out.append((k, _val(make(method), d)))
    return out


def _val(metric: M.Metric, d: pd.DataFrame) -> float:
    try:
        return float(metric(d))
    except (KeyError, ValueError, IndexError):
        return math.nan


def _collect(root: Path, sub: str) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    base = root / sub
    if base.is_dir():
        for p in sorted(base.iterdir()):
            df = load_rows(p / "rows.parquet")
            if df is not None:
                out[p.name] = df
    return out


def fig_kappa(frames: dict[str, pd.DataFrame], out: Path) -> None:
    """Fig. 4: kappa curve; UAR_truth (top) and cost ratio (bottom) of ReVal against the safety factor."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex="col", constrained_layout=True)
    fig.suptitle("Safety factor kappa: UAR_truth and cost ratio of ReVal (A7 sweep)")
    for r, (make, yl) in enumerate(
        ((M.uar_truth, "UAR_truth (1)"), (M.cost_ratio, "plan cost / B0 cost (1)"))
    ):
        axes[r][0].set_ylabel(yl)
        for ax, t in zip(axes[r], TIERS, strict=True):
            ax.set_title(TIER_TITLE[t], fontsize=10)
            ax.grid(color="#dddddd", linewidth=0.6)
            pts = [(float(_natural(k)[0]), v) for k, v in _sweep(frames, t, make)] if frames else []
            pts = [p for p in pts if not math.isnan(p[1])]
            if not pts:
                _na(ax)
                continue
            ax.plot(*zip(*pts, strict=True), marker="o", color=SERIES[0])
    axes[1][0].set_xlabel("kappa (1)")
    axes[1][1].set_xlabel("kappa (1)")
    _save(fig, out)


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float, float]:
    """(p, lo, hi) Wilson score interval; NaNs when n == 0."""
    if n <= 0:
        return math.nan, math.nan, math.nan
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def fig_coverage(cov: pd.DataFrame | None, out: Path) -> None:
    """Fig. 5: empirical conformal coverage per length class against the nominal level (Wilson 95% CI)."""
    fig, axes = _panels("Empirical conformal coverage per cycle-length class", "coverage (1)", "length class")
    for ax, t in zip(axes, TIERS, strict=True):
        d = cov[cov["tier"] == t] if cov is not None else None
        if d is None or d.empty:
            _na(ax)
            continue
        d = d.reset_index(drop=True)
        for i, r in d.iterrows():
            p, lo, hi = wilson(float(r["covered"]), float(r["n"]))
            ax.errorbar([i], [p], yerr=[[p - lo], [hi - p]], fmt="o", color=SERIES[0], capsize=3)
        ax.axhline(float(d["nominal"].iloc[0]), color="#D55E00", ls="--", lw=1, label="nominal level")
        ax.set_xticks(range(len(d)), [str(x) for x in d["length_class"]])
        ax.set_ylim(0, 1.05)
    axes[0].legend(fontsize=8)
    _save(fig, out)


def rq4_cells(rq4: pd.DataFrame) -> pd.DataFrame:
    """Per cell: accepted, wrong acceptances (accepted and truth), UAR_truth and Wilson interval."""
    rows = []
    for cell, g in rq4.groupby("cell", sort=True):
        acc = g[g["accepted"].astype(bool)]
        wrong = int(acc["truth"].astype(bool).sum())
        p, lo, hi = wilson(wrong, len(acc))
        rows.append({"cell": cell, "n_runs": len(g), "n_accepted": len(acc), "uar": p, "lo": lo, "hi": hi})
    return pd.DataFrame(rows)


def fig_rq4(rq4: pd.DataFrame | None, out: Path) -> None:
    """Fig. 6: the RQ4 2 x 2, UAR_truth by {O1, O3} x {point, gated} (Tier B only)."""
    fig, ax = plt.subplots(figsize=(6, 4), constrained_layout=True)
    ax.set_title("RQ4: UAR_truth of optimizer designs, Tier B (Wilson 95% CI)", fontsize=10)
    ax.set_ylabel("UAR_truth (1)")
    ax.grid(axis="y", color="#dddddd", linewidth=0.6)
    if rq4 is None or rq4.empty:
        _na(ax)
        _save(fig, out)
        return
    cells = rq4_cells(rq4)
    for i, (var, mk) in enumerate((("O1", "o"), ("O3", "s"))):
        for j, rule in enumerate(("point", "gated")):
            r = cells[cells["cell"] == f"{var}/{rule}"]
            if r.empty or math.isnan(float(r["uar"].iloc[0])):
                continue
            p, lo, hi = (float(r[c].iloc[0]) for c in ("uar", "lo", "hi"))
            ax.errorbar([j + (i - 0.5) * 0.2], [p], yerr=[[p - lo], [hi - p]], fmt=mk,
                        color=SERIES[i], capsize=3, label=var if j == 0 else None)  # fmt: skip
    ax.set_xticks([0, 1], ["point acceptance", "ReVal-gated acceptance"])
    ax.set_xlim(-0.6, 1.6)
    ax.legend(title="variant", fontsize=8)
    _save(fig, out)


def fig_cost_sensitivity(frames: dict[str, pd.DataFrame], out: Path) -> None:
    """Fig. 7: cost ratio against B0 for each bench-cost profile (a missing profile set renders as n/a)."""
    fig, axes = _panels(
        "Cost sensitivity per bench-cost profile", "plan cost / B0 cost (1)", "bench cost profile"
    )
    tags = sorted(frames, key=_natural)
    for ax, t in zip(axes, TIERS, strict=True):
        if not tags:
            _na(ax)
            continue
        for i, m in enumerate(("reval", "B1", "B2", "B4")):
            ys = [_val(M.cost_ratio(m), frames[k][frames[k]["tier"] == t]) for k in tags]
            if all(math.isnan(y) for y in ys):
                continue
            col, mk = STYLE.get(m, (SERIES[i], MARKERS[i]))
            ax.plot(range(len(tags)), ys, marker=mk, color=col, label=m)
        ax.set_xticks(range(len(tags)), tags)
    axes[0].legend(fontsize=8)
    _save(fig, out)


def _profiles(root: Path, main: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Cost-profile frames: ``cost_profiles/<tag>`` dirs plus non-default tags inside the main file."""
    out = _collect(root, "cost_profiles")
    if "cost_profile" in main.columns:
        for tag, g in main.groupby("cost_profile"):
            if tag != "default":
                out.setdefault(str(tag), g)
    return out


def generate(root: Path, n_boot: int, delta: float = DELTA) -> list[Path]:
    """Write every figure and table under ``root``; returns the paths written."""
    main = load_rows(root / "rows.parquet")
    if main is None:
        raise FileNotFoundError(f"{root / 'rows.parquet'} not found")
    main = main[main["cost_profile"].isin(["default"])] if "default" in set(main["cost_profile"]) else main
    fig, tab = root / "figures", root / "tables"
    tab.mkdir(parents=True, exist_ok=True)
    cov_p, rq4_p = root / "conformal_coverage.parquet", root / "rq4.parquet"
    cov = pd.read_parquet(cov_p) if cov_p.exists() else None
    rq4 = pd.read_parquet(rq4_p) if rq4_p.exists() else None
    fig_cost_ratio(main, fig / "fig1_cost_ratio.png", n_boot)
    fig_impact(main, fig / "fig2_impact.png", n_boot)
    (tab / "ablation.tex").write_text(ablation_table(main, _collect(root, "ablations")), encoding="utf-8")
    fig_kappa(_collect(root, "kappa"), fig / "fig4_kappa_curve.png")
    fig_coverage(cov, fig / "fig5_conformal_coverage.png")
    fig_rq4(rq4, fig / "fig6_rq4_2x2.png")
    fig_cost_sensitivity(
        _profiles(root, pd.read_parquet(root / "rows.parquet")), fig / "fig7_cost_sensitivity.png"
    )
    (tab / "h1.tex").write_text(h1_table(main, n_boot, delta=delta), encoding="utf-8")
    return sorted([*fig.glob("*.png"), *tab.glob("*.tex")])


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bench.analysis.figures", description=__doc__.splitlines()[0])
    ap.add_argument("--results", type=Path, required=True, help="bench/results/<hash>")
    ap.add_argument(
        "--delta", type=float, default=DELTA, help="non-inferiority margin (pre-registered value)"
    )
    ap.add_argument("--n-boot", type=int, default=10_000, help="bootstrap resamples (docs/06: 10000)")
    args = ap.parse_args(argv)
    for p in generate(args.results, args.n_boot, args.delta):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
