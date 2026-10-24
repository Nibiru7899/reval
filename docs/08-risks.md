# 08 — Risk register

Scores: likelihood (L) and impact (I) on a 1–3 scale. Review at every supervisor meeting.

| # | Risk | L | I | Mitigation | Trigger → fallback |
|---|---|---|---|---|---|
| R1 | Prior-art review finds a tool that already does the full combination | 2 | 3 | Phase 0 review with a kill criterion | Pivot the contribution to tolerance-aware invalidation or ReValBench alone |
| R2 | LPTN identification unstable or poor | 2 | 2 | Start week 5, good initial values from physics, bounded least squares | 2-node LPTN by end of week 5; document it |
| R3 | Conformal coverage on held-out profiles far below nominal | 2 | 2 | Peak-window calibration, per-length-class quantiles | Report the honest coverage. Use Mondrian / CQR variants. Widen α. It's a finding, not a failure. |
| R4 | Optimizer O1 doesn't actually go out of domain | 1 | 1 | Use a wider duty-cycle parameter space | Report it. The RQ4 story then rests on the recorded-cycle subjects. |
| R5 | Tolerance carry-forward causes unsupported accepts | 2 | 2 | κ ablation, conservative default | That is a research result. Recommend a κ value or disable by default. |
| R6 | Scope creep in the UI | 3 | 2 | UI starts only after M4. Cut line #4. | Static HTML report |
| R7 | Ground truth seen as circular (Tier B) | 2 | 3 | Structural difference, injected model-form error, separate reporting, Tier A as the primary result | Make Tier A the headline. Tier B becomes supplementary. |
| R8 | Benchmark runtime too long | 2 | 1 | Cache producer results by `(producer, inputs-hash)`, parallel runner | Reduce instances per type to 15 |
| R9 | Dataset license or access problem | 1 | 3 | Check the license in week 1. Never redistribute data. | Use the published IEEE DataPort copy, or a synthetic-only fallback (weakens the project) |
| R10 | Time lost to Windows/tooling issues | 2 | 1 | `uv`, pinned versions, CI on Linux + Windows | Use WSL2 for heavy jobs |
| R11 | Over-claiming in the report ("ReVal proves safety") | 2 | 3 | Disclaimers in every report. AGENTS.md rule. Supervisor review of wording. | — |
| R12 | Solo-developer bus factor / burnout | 2 | 3 | Weekly logs, small milestones, buffer weeks 18 and 30 | Apply cut lines early, not late |
