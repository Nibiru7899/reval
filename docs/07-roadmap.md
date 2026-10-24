# 07 — Roadmap

**Assumptions:** one student, ~15–20 h/week, a two-semester capstone (~30 weeks). A one-semester (16-week) cut is given at the end.
Weeks are relative. Map them onto your institution's calendar and its proposal, interim, and final deadlines.

Each milestone has a **Definition of Done (DoD)**. A milestone isn't done until its DoD holds *and* CI is green.

## Phase 0 — Foundations (weeks 1–2)

| Week | Work |
|---|---|
| 1 | Prior-art review (protocol in [01](01-problem-and-prior-art.md) §4). Verify or drop the ⚠️ references. Download the dataset. EDA notebook: profile lengths, operating-region coverage, peak-temperature distributions. |
| 2 | Write a 2–3 page proposal from `docs/00` and `docs/01`. Fix the splits. Choose declared limits. Supervisor meeting: confirm scope and the kill criterion. |

**M0 DoD:** `related-work.csv` has ≥ 25 rows. `splits.yaml` is committed. The proposal is approved. The repo scaffold passes CI.

## Phase 1 — Motor domain (weeks 3–6)

| Week | Work |
|---|---|
| 3 | Data pipeline (`download → validate schema → parquet`). Feature engineering (EWMA). Ridge M1. Per-profile evaluation harness. |
| 4 | M2/M3. Peak-over-window evaluation. Split-conformal on peaks. Empirical coverage on `test`. |
| 5 | 4-node LPTN: simulator + identification + validation + δ band. Fallback decision by end of week. |
| 6 | Drive map. Duty-cycle generator. Optimizer O1/O2/O3. Applicability domain (range box + kNN). |

**M1 DoD:** `python -m motor.train` reproduces the model metrics from a clean clone, with a recorded hash. Coverage tables for α ∈ {0.1, 0.05}.
The LPTN test MSE is reported. One figure shows O1's optimum outside the domain (or an honest note that it isn't).

## Phase 2 — Core engine (weeks 7–10)

| Week | Work |
|---|---|
| 7 | Domain models (Pydantic, frozen). Manifest schema + loader with `pint` units. Hashers (`file`, `yaml-fields`, `dataframe`, `model`). |
| 8 | Evidence graph (E1). Producer SDK (`@reval.producer`, `Context.load` guard). SQLite store + Alembic. |
| 9 | Verdicts + status rules (E3 without AD/conformal plumbing). Policies. `reval status`. |
| 10 | Property tests I1–I7 (Hypothesis). Wire motor producers into `examples/motor_thermal/reval.yaml`. |

**M2 DoD:** `reval status` on the motor example prints every claim with its reasons. I1–I4 and I7 pass as property tests. Coverage on `core` ≥ 90 %.

## Phase 3 — Change impact (weeks 11–14)

| Week | Work |
|---|---|
| 11 | Diff → `ChangeSet`. Git snapshot reader (`reval diff REV_A REV_B`). |
| 12 | Freshness classes: exact, out-of-scope, invalidated. Fail-closed handling of `Unknown`. |
| 13 | Tolerance carry-forward. LPTN sensitivity estimation script → `Tolerance` records with `source`. I5 property test. |
| 14 | **Interim demo + report.** Show a coolant change making the right claims stale and leaving the shaft claim alone. |

**M3 DoD:** a scripted demo runs in one command (`examples/motor_thermal/demo_change.ps1` / `.sh`). The interim report is submitted.

## Phase 4 — Validity + planner (weeks 15–18)

| Week | Work |
|---|---|
| 15 | AD + conformal integrated into ML verdicts. AD report in reasons. |
| 16 | Candidate generation. CP-SAT model (min cost + budgeted). Greedy + rerun-all planners. |
| 17 | `reval plan`, `reval run` (job runner, append-only evidence). Re-assessment loop. I6 property test. |
| 18 | Reports: JSON (canonical) → Markdown/HTML. Report hash. Mandatory disclaimer. Buffer week. |

**M4 DoD:** `reval diff → plan → run → report` works end to end on the motor example. The planner is unit-tested against
brute force on small random instances (exact optimum match).

## Phase 5 — ReValBench (weeks 19–23)

| Week | Work |
|---|---|
| 19 | **Pre-registration committed.** Scenario generator for T1–T6, T10, T11 (Tier A). |
| 20 | Virtual world model. T6–T9, T12 (Tier B). Truth oracles. |
| 21 | Baselines B0–B4. Metric computation. Parallel runner (`joblib`) with result caching. |
| 22 | Full runs + ablations A1–A7. Cost sensitivity. |
| 23 | Analysis notebooks → figures and tables (scripted, regenerable). |

**M5 DoD:** `python -m bench.run --config bench/configs/full.yaml` regenerates every figure and table in the paper from scratch.
Results are archived with hashes.

## Phase 6 — Workspace + integration (weeks 20–26, in parallel with Phase 5 as time allows)

| Week | Work |
|---|---|
| 20–21 | FastAPI endpoints over the services ([09](09-api-and-ui.md)). OpenAPI → generated TS client. |
| 22–23 | Web UI: claim board, claim detail (justification tree, envelope plot), change timeline. |
| 24 | Graph explorer (`@xyflow/react`). Planner page with budget slider. |
| 25 | GitHub Action (`reval diff` on PR → Markdown comment). Docker Compose (API + Postgres + UI). |
| 26 | Usability check (RQ5) if you're doing it. Fix the top 5 issues. |

**M6 DoD:** `docker compose up` gives a working workspace on the motor example. The demo PR in the repo shows the action's comment.

## Phase 7 — Write-up and release (weeks 27–30)

| Week | Work |
|---|---|
| 27 | Paper draft ([research/paper-outline.md](research/paper-outline.md)). Final-report chapters reuse the paper sections. |
| 28 | Docs site (MkDocs Material): quickstart, concepts, motor tutorial, "add ReVal to your project". `pip install` from a wheel. |
| 29 | Poster, 5-minute demo video, defense slides. Tag `v1.0.0`. arXiv preprint (with supervisor approval). |
| 30 | Defense. Buffer. |

## Weekly rhythm

- **Monday:** pick the week's issues from the milestone. **Friday:** a 5-line log in `docs/log/YYYY-Www.md` (done / blocked / next / numbers / risks).
- Meet the supervisor every 2 weeks with a demo of something that runs, not just slides.
- Every result number in a report is produced by a committed script. No hand-copied numbers.

## Cut lines (what to drop, in order, if behind schedule)

1. The TNN model (M4), the sequential planner, the second domain (stretch goals: drop first)
2. RQ5 usability study → replace with a heuristic walkthrough
3. GitHub Action and Docker Compose → keep the CLI only
4. Web UI → reduce to a static HTML report viewer, generated by `reval report --html`
5. Tier B → reduce to T7/T8 only

**Never cut:** the deterministic core, fail-closed semantics, Tier A benchmark, baselines B0/B1/B2, pre-registration, reproducibility.

## One-semester (16-week) variant

| Weeks | Scope |
|---|---|
| 1–2 | Phase 0 |
| 3–5 | Phase 1 with M1 only, a 2-node LPTN, no optimizer O3 |
| 6–8 | Phase 2 |
| 9–10 | Phase 3 without tolerance carry-forward (exact and out-of-scope freshness only) |
| 11–12 | Phase 4 with the CP-SAT min-cost planner only |
| 13–14 | Tier A benchmark, B0–B2, ablations A1/A3/A6 |
| 15–16 | Static HTML report, final report, demo |

In this variant, tolerance carry-forward becomes "future work". The research question narrows to field- and scope-level invalidation.
