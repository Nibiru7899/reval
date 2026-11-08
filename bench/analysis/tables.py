"""LaTeX tables for the paper (P5-15): the ablation table (A1-A8) and the H1 four-part result table.

Every number is computed from result parquet files by ``bench.analysis.metrics`` / ``stats``; nothing is typed
in. A missing input renders as "not available" (never as 0 and never as a pass).
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from bench.analysis import metrics as M
from bench.analysis import stats as S

NA = "not available"
ABLATIONS: tuple[tuple[str, str], ...] = (
    ("A1", "whole-artifact selectors"),
    ("A2", "no tolerance carry-forward"),
    ("A3", "no scope-based freshness"),
    ("A4", "AD gate relaxed / off"),
    ("A5", "fixed margin instead of conformal"),
    ("A6", "greedy planner"),
    ("A7", "kappa override"),
    ("A8", "CQR instead of split conformal"),
)
DISCLAIMER = (
    "Statuses mean supported by recorded evidence against the declared requirement; "
    "they are not a certification or a guarantee."
)
DELTA = 0.01  # docs/06 section 1: planned margin, re-justified from the pilot before pre-registration
COVERAGE_MARGIN = 0.02


def tex_escape(s: str) -> str:
    """Escape LaTeX special characters in a cell."""
    out = s
    for ch, rep in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#")):
        out = out.replace(ch, rep)
    return out


def num(x: float, nd: int = 3) -> str:
    """Format a float; NaN becomes 'not available'."""
    return NA if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def tex_table(header: list[str], rows: list[list[str]], caption: str, label: str) -> str:
    """Minimal booktabs table with the disclaimer as a note."""
    cols = "l" * 1 + "r" * (len(header) - 1)
    lines = [
        r"\begin{table}[ht]",
        r"\centering\small",
        rf"\caption{{{tex_escape(caption)}}}\label{{{label}}}",
        rf"\begin{{tabular}}{{{cols}}}",
        r"\toprule",
        " & ".join(tex_escape(h) for h in header) + r" \\",
        r"\midrule",
    ]
    lines += [" & ".join(tex_escape(c) for c in r) + r" \\" for r in rows]
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        rf"\par\footnotesize {tex_escape(DISCLAIMER)}",
        r"\end{table}",
        "",
    ]
    return "\n".join(lines)


def load_rows(path: Path) -> pd.DataFrame | None:
    """Read a ``rows.parquet`` or ``None`` when absent."""
    return pd.read_parquet(path) if path.exists() else None


def _tier(df: pd.DataFrame, tier: str) -> pd.DataFrame:
    return df[df["tier"] == tier]


def _safe(fn, *a, **k):  # type: ignore[no-untyped-def]
    """NaN instead of an exception for an empty/undefined slice (rendered 'not available')."""
    try:
        return fn(*a, **k)
    except (KeyError, ValueError, IndexError):
        return math.nan


def ablation_table(main: pd.DataFrame, arms: dict[str, pd.DataFrame]) -> str:
    """Per ablation and tier: ReVal cost ratio, UAR_truth, recall, coverage (vs main run)."""
    header = [
        "Id",
        "Change",
        "Tier",
        "cost/B0",
        "UAR_truth",
        "recall",
        "coverage",
        "d cost/B0",
        "d UAR_truth",
    ]
    ids = [a for a, _ in ABLATIONS]
    extra = sorted(k for k in arms if k.split("_")[0] not in ids)
    rows: list[list[str]] = []

    def vals(df: pd.DataFrame, tier: str) -> list[float]:
        d = _tier(df, tier)
        return [
            _safe(M.cost_ratio("reval"), d),
            _safe(M.uar_truth("reval"), d),
            _safe(M.impact_recall("reval"), d),
            _safe(M.decision_coverage("reval"), d),
        ]

    for tier in ("A", "B"):
        base = vals(main, tier)
        rows.append(["main", "ReVal (reference)", tier, *[num(v) for v in base], "", ""])
    for aid, desc in [*ABLATIONS, *((e, e) for e in extra)]:
        mine = {k: v for k, v in arms.items() if k == aid or k.startswith(aid + "_")}
        if aid in extra:
            mine = {aid: arms[aid]}
        if not mine:
            rows.append([aid, desc, "A/B", *[NA] * 6])
            continue
        for name in sorted(mine):
            for tier in ("A", "B"):
                v = vals(mine[name], tier)
                base = vals(main, tier)
                d_cost, d_uar = v[0] - base[0], v[1] - base[1]
                rows.append([name, desc, tier, *[num(x) for x in v], num(d_cost), num(d_uar)])
    return tex_table(
        header, rows, "Ablations A1-A8 (ReVal arm; d = ablation minus main run).", "tab:ablation"
    )


def h1_parts(df: pd.DataFrame, n_boot: int, seed: int = 0, delta: float = DELTA) -> list[dict[str, str]]:
    """The four H1 components for one tier. NaN bounds never pass (fail closed)."""
    d = prepare_tier(df)
    out: list[dict[str, str]] = []

    def part(name: str, stat: str, bound: float, ok: bool) -> None:
        out.append({"part": name, "statistic": stat, "bound": num(bound), "holds": "yes" if ok else "no"})

    def samples(metrics, combine):  # type: ignore[no-untyped-def]
        try:
            return S.bootstrap_samples(d, metrics, combine, n=n_boot, seed=seed)
        except (KeyError, ValueError, IndexError):
            return math.nan, S.np.full(n_boot, math.nan)

    est, s = samples([M.log_cost_ratio("reval", "B1")], lambda x: x)
    ub = S.percentile_interval(s)[1]
    part("1 cost: mean log(C_ReVal/C_B1), 95% CI upper", num(est), ub, ub < 0)
    est, s = samples([M.uar_truth("reval"), M.uar_truth("B0")], lambda a, b: a - b)
    ub = S.one_sided_bound(s, "upper")
    part(f"2 UAR_truth diff vs B0, 97.5% upper < {delta}", num(est), ub, S.non_inferior(ub, delta))
    est, s = samples([M.uar_evidence("reval")], lambda x: x)
    ub = S.one_sided_bound(s, "upper")
    part(f"3 UAR_evidence, 97.5% upper < {delta}", num(est), ub, S.non_inferior(ub, delta))
    est, s = samples([M.decision_coverage("reval"), M.decision_coverage("B0")], lambda a, b: a - b)
    lb = S.one_sided_bound(s, "lower")
    part(
        f"4 coverage diff vs B0, 97.5% lower >= -{COVERAGE_MARGIN}",
        num(est),
        lb,
        bool(lb >= -COVERAGE_MARGIN),
    )
    return out


def prepare_tier(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows the metrics exclude (WAIVED) so slices are consistent."""
    return df.reset_index(drop=True)


def h1_table(main: pd.DataFrame, n_boot: int, seed: int = 0, delta: float = DELTA) -> str:
    """Four-part H1 table, Tier A and Tier B separately (never pooled); H1 holds only if all four hold."""
    header = ["Tier", "Component", "estimate", "bound", "holds"]
    rows: list[list[str]] = []
    for tier in ("A", "B"):
        d = _tier(main, tier)
        if d.empty:
            rows.append([tier, NA, NA, NA, NA])
            continue
        parts = h1_parts(d, n_boot, seed, delta)
        for p in parts:
            rows.append([tier, p["part"], p["statistic"], p["bound"], p["holds"]])
        ok = S.intersection_union({p["part"]: p["holds"] == "yes" for p in parts})
        rows.append([tier, "H1 (all four parts)", "", "", "yes" if ok else "no"])
    cap = f"H1 components (delta = {delta}); supported by recorded evidence against the declared requirement."
    return tex_table(header, rows, cap, "tab:h1")
