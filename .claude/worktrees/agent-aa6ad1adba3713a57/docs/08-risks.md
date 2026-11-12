# 08 — Risk register

Scores: likelihood (L) and impact (I) on a 1–3 scale. Review at every fortnightly self-review.

| # | Risk | L | I | Mitigation | Trigger → fallback |
|---|---|---|---|---|---|
| R1 | Prior-art review finds a tool that already does the full combination | 2 | 3 | Phase 0 review with a kill criterion | Pivot the contribution to tolerance-aware invalidation or ReValBench alone |
| R2 | LPTN identification unstable or poor | 2 | 2 | Start week 5, good initial values from physics, bounded least squares | 2-node LPTN by end of week 5; document it |
| R3 | Conformal coverage on held-out profiles far below nominal, or too few calibration windows (n < ⌈1/α⌉ − 1 ⇒ unbounded interval) | 2 | 2 | Peak-window calibration, per-length-class quantiles, merge length classes when n is small | Report the honest coverage. Use Mondrian / CQR variants. Widen α. It's a finding, not a failure. |
| R4 | Optimizer O1 doesn't actually go out of domain | 1 | 1 | Use a wider duty-cycle parameter space | Report it. RQ4 then reports Tier A coverage-only evidence (recorded test cycles) plus the Tier B 2×2 result. |
| R5 | Tolerance carry-forward causes unsupported accepts | 2 | 2 | κ ablation (A7), conservative default. Sensitivities and physics evidence share the design LPTN's model-form error, so A2/A7 are primary ablations. | That is a research result. Recommend a κ value or disable by default. |
| R6 | Scope creep in the UI | 3 | 2 | Phase 6 starts only after the M5 DoD (earliest week 24). Cut line #5. | Static HTML report |
| R7 | Ground truth seen as circular (Tier B) | 2 | 3 | Structural difference, injected model-form error, world calibrated on train + reserve only, Tier B ML retrained on world trajectories, separate reporting, Tier A as the primary result | Make Tier A the headline. Tier B becomes supplementary. |
| R8 | Benchmark runtime too long (B0 reruns LPTN identification and ML training per scenario) | 3 | 2 | Producer cache keyed by (producer code hash, input hash). LPTN identification and ML training shared across scenarios with identical inputs. Parallel runner. The week-21 pilot measures wall-clock per scenario and sets instance counts before pre-registration. | Reduce instances per type to 15. Keep ≥ 30 base snapshots. |
| R9 | Dataset license or access problem | 1 | 3 | License is CC BY-SA 4.0 (Kaggle v3). Never redistribute data or derived data. ReValBench publishes generators only. | Use the Paderborn LEA / `upb-lea` GitHub links, or contact the authors. Synthetic-only fallback as a last resort (weakens the project). |
| R10 | Time lost to Windows/tooling issues | 2 | 1 | `uv`, pinned versions, CI on Linux + Windows | Use WSL2 for heavy jobs |
| R11 | Over-claiming in the report ("ReVal proves safety") | 2 | 3 | Disclaimers in every report. AGENTS.md rule. Re-read every public text against rule 9 before publishing; ask an outside reader if possible. | — |
| R12 | Solo-developer bus factor / burnout | 2 | 3 | Weekly logs, small milestones, real buffer weeks 18 and 24, Phase 6 gated on M5 | Apply cut lines early, not late |
