# ReValBench

A benchmark of controlled engineering changes with ground truth (see `docs/06-evaluation.md`). Built in Phase 5 (tasks `P5-*`).

Planned layout:

```
configs/        smoke.yaml, full.yaml, ablations/*.yaml
scenarios/      generator for change types T1–T12
oracles/        evidence oracle (rerun-all), truth oracles (Tier A measured, Tier B world model)
world/          Tier B virtual-world thermal model
baselines/      B0–B4
run.py          parallel runner with result cache
analysis/       metrics, bootstrap, figures and tables
results/        generated, git-ignored
```
