"""RQ4 / H3 optimizer experiment (P5-20, docs/06 sections 1 and 6): {O1, O3} x {point, gated}, Tier B.

One seeded optimizer run per (variant, seed, limit level) yields one proposed design. Both acceptance rules
judge that same proposal, so the point and gated rows of a variant are paired by ``run_id``:

* point acceptance: the model's point peak is within the limit (the optimizer's own O1 constraint).
* ReVal-gated acceptance: the conformal upper bound is within the limit **and** the design lies inside the
  model's applicability domain. An unbounded interval is not accepted (fail closed).

``truth`` is ``True`` when the world's noise-free peak violates the limit, so a *wrong acceptance* is
``accepted & truth`` (UAR_truth numerator). Nothing here decides a status; this is an experiment harness.
Run via ``run_rq4`` with the Tier B project's model, conformal, AD and drive map plus a truth function
(``world_truth_fn`` builds one from a ``World``).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import yaml
from motor.cycles import blocks
from motor.optimizer import AMBIENT_C, COOLANT_C, LIMIT_KEYS, optimize

from bench.world.model import PhysicalParams, World

VARIANTS: tuple[Literal["O1"], Literal["O3"]] = ("O1", "O3")
ACCEPTANCE: tuple[str, str] = ("point", "gated")
CELLS: tuple[str, ...] = tuple(f"{v}/{a}" for v in VARIANTS for a in ACCEPTANCE)
POINT_TOL_K = 0.5  # DE solves the penalized problem only approximately (same slack as the optimizer tests)

TruthFn = Callable[[Mapping[str, Any], Mapping[str, float]], bool]  # (subject_params, limits) -> violated


@dataclass(frozen=True)
class Rq4Config:
    """Experiment design. N per cell = ``len(seeds) * len(limit_offsets_k)``."""

    seeds: tuple[int, ...]
    limit_offsets_k: tuple[float, ...]  # K, added to every base limit
    base_limits: Mapping[str, float]
    popsize: int = 15
    maxiter: int = 50
    min_runs_per_cell: int = 50

    def __post_init__(self) -> None:
        n = len(self.seeds) * len(self.limit_offsets_k)
        if n < self.min_runs_per_cell:
            raise ValueError(f"{n} runs per cell < min_runs_per_cell={self.min_runs_per_cell}")


def load_config(path: Path) -> Rq4Config:
    """Read ``bench/configs/rq4.yaml``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    s = raw["seeds"]
    return Rq4Config(
        seeds=tuple(range(int(s["start"]), int(s["start"]) + int(s["count"]))),
        limit_offsets_k=tuple(float(x) for x in raw["limit_offsets_k"]),
        base_limits={k: float(v) for k, v in raw["base_limits"].items()},
        popsize=int(raw["popsize"]),
        maxiter=int(raw["maxiter"]),
        min_runs_per_cell=int(raw["min_runs_per_cell"]),
    )


def world_truth_fn(
    world: World,
    physical: PhysicalParams,
    drive_map: Any,
    coolant: float = COOLANT_C,
    ambient: float = AMBIENT_C,
) -> TruthFn:
    """Truth from the world's noise-free pm peak (the optimizer's head target) for a proposed duty cycle."""

    def truth(subject_params: Mapping[str, Any], limits: Mapping[str, float]) -> bool:
        cyc = blocks(subject_params)
        x = drive_map.to_inputs(cyc["torque"].to_numpy(), cyc["motor_speed"].to_numpy(), coolant, ambient)
        peak = float(world.simulate(x, physical)["pm"].max())
        return peak > float(limits[LIMIT_KEYS["pm"]])  # strict, as bench.oracles.truth.violated for "<="

    return truth


def run_rq4(
    cfg: Rq4Config,
    model: Any,
    conformal: Any,
    ad: Any,
    drive_map: Any,
    bounds: Sequence[tuple[float, float]],
    truth_fn: TruthFn,
) -> pd.DataFrame:
    """Run the 2 x 2 experiment; one row per (cell, optimizer run)."""
    rows: list[dict[str, Any]] = []
    for variant in VARIANTS:
        for seed in cfg.seeds:
            for offset in cfg.limit_offsets_k:
                limits = {k: float(v) + offset for k, v in cfg.base_limits.items()}
                limit = limits[LIMIT_KEYS["pm"]]
                res = optimize(
                    variant, model, conformal, ad, drive_map, limits, bounds,
                    seed=seed, popsize=cfg.popsize, maxiter=cfg.maxiter,
                )  # fmt: skip
                truth = bool(truth_fn(res.subject_params, limits))
                accept = {
                    "point": res.pred_peak <= limit + POINT_TOL_K,
                    "gated": res.upper is not None
                    and res.upper <= limit + POINT_TOL_K
                    and res.ad_report.inside,
                }
                for rule in ACCEPTANCE:
                    rows.append(
                        {
                            "cell": f"{variant}/{rule}",
                            "variant": variant,
                            "acceptance": rule,
                            "run_id": f"{variant}-s{seed}-d{offset:+g}",
                            "seed": seed,
                            "limit_offset_k": offset,
                            "limit": limit,
                            "accepted": bool(accept[rule]),
                            "truth": truth,
                            "pred_peak": res.pred_peak,
                            "upper": res.upper,
                            "ad_inside": bool(res.ad_report.inside),
                        }
                    )
    return pd.DataFrame(rows)


def main(argv: Sequence[str] | None = None) -> None:
    """Load the config and report the design; the Tier B workspace wiring is done by the pilot (P5-17)."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=Path("bench/configs/rq4.yaml"))
    cfg = load_config(ap.parse_args(argv).config)
    n = len(cfg.seeds) * len(cfg.limit_offsets_k)
    print(f"RQ4: {len(CELLS)} cells x {n} runs; call run_rq4() with the Tier B project's artifacts.")


if __name__ == "__main__":
    main()
