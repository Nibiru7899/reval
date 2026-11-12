"""P5-15: every figure/table is regenerated from a tiny synthetic results directory."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("matplotlib")

from bench.analysis import figures
from bench.analysis.tables import tex_escape
from bench.metrics.records import ClaimRecord, to_frame

METHODS = ("reval", "B0", "B1", "B2", "B3", "B4")


def _rows(tier: str, seed: int, profile: str = "default", scale: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    recs: list[ClaimRecord] = []
    for ct in ("T1", "T5"):
        for snap in range(2):
            for k in range(2):
                sid = f"{tier}-{ct}-{snap}-{k}"
                b0_cost = 100.0
                cost = {"reval": 30.0 * scale, "B0": b0_cost, "B1": 60.0, "B2": 40.0, "B3": 0.0, "B4": 30.0}
                for m in METHODS:
                    for c in range(3):
                        truth = None if (tier == "A" and c == 2) else bool(rng.random() < 0.2)
                        acc = m == "B3" or bool(rng.random() < 0.7)
                        recs.append(
                            ClaimRecord(
                                scenario_id=sid, change_type=ct, tier=tier, base_snapshot=f"{tier}{snap}",
                                method=m, claim_id=f"C{c}", status_before="supported",
                                status_after="supported" if acc else "inconclusive", accepted=acc,
                                b0_accepted=bool(rng.random() < 0.7), truly_affected=bool(c % 2 == 0),
                                predicted_affected=bool(c % 2 == 0 or rng.random() < 0.3),
                                truth_violated=truth, cost=cost[m], b0_cost=b0_cost,
                                n_bench_runs=1, cost_profile=profile,
                            )
                        )  # fmt: skip
    return to_frame(recs)


def _both(sa: int, sb: int, profile: str = "default", scale: float = 1.0) -> pd.DataFrame:
    return pd.concat([_rows("A", sa, profile, scale), _rows("B", sb, profile, scale)], ignore_index=True)


def _build(root: Path) -> None:
    root.mkdir(parents=True)
    _both(1, 2).to_parquet(root / "rows.parquet")
    for aid in ("A1", "A2", "A5", "A6", "A7_k1.0"):  # A3, A4, A8 deliberately absent
        d = root / "ablations" / aid
        d.mkdir(parents=True)
        _both(3, 4).to_parquet(d / "rows.parquet")
    for kap in (1.0, 1.5, 2.0):
        d = root / "kappa" / f"k{kap}"
        d.mkdir(parents=True)
        _both(5, 6).to_parquet(d / "rows.parquet")
    for tag, scale in (("bench20", 1.0), ("bench100", 1.5), ("bench500", 2.0)):
        d = root / "cost_profiles" / tag
        d.mkdir(parents=True)
        _both(7, 8, tag, scale).to_parquet(d / "rows.parquet")
    rng = np.random.default_rng(9)
    cov = [
        {"tier": t, "length_class": lc, "n": 40, "covered": int(rng.integers(30, 40)), "nominal": 0.9}
        for t in ("A", "B")
        for lc in ("short", "medium", "long")
    ]
    pd.DataFrame(cov).to_parquet(root / "conformal_coverage.parquet")
    rq4 = []
    for v in ("O1", "O3"):
        for r in range(6):
            truth = bool(rng.random() < 0.4)
            for rule in ("point", "gated"):
                rq4.append(
                    {
                        "cell": f"{v}/{rule}", "variant": v, "acceptance": rule, "run_id": f"{v}-{r}",
                        "accepted": bool(rng.random() < (0.8 if rule == "point" else 0.4)), "truth": truth,
                    }
                )  # fmt: skip
    pd.DataFrame(rq4).to_parquet(root / "rq4.parquet")


EXPECTED = [
    "figures/fig1_cost_ratio.png",
    "figures/fig2_impact.png",
    "tables/ablation.tex",
    "figures/fig4_kappa_curve.png",
    "figures/fig5_conformal_coverage.png",
    "figures/fig6_rq4_2x2.png",
    "figures/fig7_cost_sensitivity.png",
    "tables/h1.tex",
]


def test_all_outputs_generated(tmp_path: Path) -> None:
    root = tmp_path / "abc123"
    _build(root)
    assert figures.main(["--results", str(root), "--n-boot", "50"]) == 0
    for rel in EXPECTED:
        p = root / rel
        assert p.exists() and p.stat().st_size > 0, rel
    abl = (root / "tables/ablation.tex").read_text(encoding="utf-8")
    for aid in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"):
        assert aid in abl
    assert abl.count("not available") >= 3  # A3, A4, A8
    h1 = (root / "tables/h1.tex").read_text(encoding="utf-8")
    assert "supported by recorded evidence" in h1
    assert "safe" not in (abl + h1).lower().replace("unsafe", "")


def test_deterministic_tables(tmp_path: Path) -> None:
    root = tmp_path / "r"
    _build(root)
    figures.main(["--results", str(root), "--n-boot", "50"])
    first = (root / "tables/h1.tex").read_text(encoding="utf-8")
    figures.main(["--results", str(root), "--n-boot", "50"])
    assert (root / "tables/h1.tex").read_text(encoding="utf-8") == first


def test_missing_optional_inputs_render_not_available(tmp_path: Path) -> None:
    root = tmp_path / "only_rows"
    root.mkdir()
    _both(1, 2).to_parquet(root / "rows.parquet")
    assert figures.main(["--results", str(root), "--n-boot", "20"]) == 0
    for rel in EXPECTED:
        assert (root / rel).exists(), rel
    assert "not available" in (root / "tables/ablation.tex").read_text(encoding="utf-8")


def test_missing_rows_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        figures.main(["--results", str(tmp_path)])


def test_tex_escape() -> None:
    assert tex_escape("A_1 & 50%") == r"A\_1 \& 50\%"
