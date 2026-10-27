# 07 — Roadmap

**Assumptions:** a personal, self-paced project. One person, ~15–20 h/week, ~30 weeks. A short (16-week) variant is given at the end.
Weeks are relative. There are no external deadlines; the milestones and their DoDs are the checkpoints.
Task-level specs are in `docs/tasks/` (index: `docs/tasks/BACKLOG.md`). Where this roadmap and a task file disagree on detail, the task file wins.

Each milestone has a **Definition of Done (DoD)**. A milestone isn't done until its DoD holds *and* CI is green.

## Phase 0 — Foundations (weeks 1–2)

| Week | Work |
|---|---|
| 1 | Prior-art review (protocol in [01](01-problem-and-prior-art.md) §4). Check the dataset license on Kaggle (CC BY-SA 4.0). The dataset is already downloaded (no token needed; P0-03 done). |
| 2 | Write a 1-page scope note (P0-07): the kill-criterion outcome and the 30- or 16-week variant. Declared limits are chosen later (week 4, after EDA and splits). |

**M0 DoD:** `related-work.csv` has ≥ 25 rows. The scope note is written and signed off by you against its checklist (P0-07 depends only on the prior-art review, P0-04). The raw dataset is downloaded. The repo scaffold passes CI.
(The splits, `splits.yaml`, the EDA notebook and the declared limits, `params/limits.yaml`, come in weeks 3–4, tasks P1-02, P0-05 and P0-06.)

## Phase 1 — Motor domain (weeks 3–6)

| Week | Work |
|---|---|
| 3 | Domain base + errors (P2-01, needed by the data loader). Data pipeline (`download → validate schema → parquet`). Profile-level splits. EDA notebook (P0-05). Feature engineering (EWMA, `adjust=False`). Ridge M1. Per-profile evaluation harness. |
| 4 | Choose declared limits from the EDA (P0-06; human). M2/M3. Peak-over-window evaluation. Split-conformal on peaks (`reval.uq.conformal`). Empirical coverage on `test`. |
| 5 | 4-node LPTN: simulator + identification + validation + δ band, with coolant flow via `params/cooling.yaml#/flow_scale`. Fallback decision by end of week. |
| 6 | Drive map. Duty-cycle generator. Optimizer O1/O2/O3. Applicability domain (`reval.uq.domain`: range box + kNN). |

**M1 DoD:** EDA notebook committed, declared limits chosen (`params/limits.yaml`). `python examples/motor_thermal/scripts/reproduce_m1.py` reproduces the model metrics from a clean clone (after the data download), with a recorded hash.
Coverage tables for α ∈ {0.1, 0.05}. The LPTN test MSE is reported. One figure shows O1's optimum outside the domain (or an honest note that it isn't).

## Phase 2 — Core engine (weeks 7–10)

| Week | Work |
|---|---|
| 7 | Domain models (Pydantic, frozen; the base and errors already exist from week 3), selectors. Manifest schema + loader with `pint` units. Hashers (`file`, `yaml-fields`, `dataframe`, `model`). |
| 8 | Evidence graph (E1). Producer SDK (`@reval.producer`, `Context.load` guard). Snapshot builder. SQLite store (document tables, `create_all`; Alembic comes in Phase 6). |
| 9 | Verdicts + status rules (E3). Policies. `reval snapshot --write/--check`, `reval status`, `reval run --all`. |
| 10 | Property tests I1, I2, I4 (Hypothesis). Wire motor producers into `examples/motor_thermal/reval.yaml`. |

**M2 DoD:** `reval status` on the motor example prints every claim with its reasons. The I1, I2, and I4 property tests pass (I3 and I7 need
the Phase 3 diff and land there). Coverage on `core` ≥ 90 %, enforced with `--cov-fail-under`.

## Phase 3 — Change impact (weeks 11–14)

| Week | Work |
|---|---|
| 11 | Diff → `ChangeSet`. Git lock reader (`reval.lock.json`, ADR 0005). `reval diff REV_A REV_B`. |
| 12 | Freshness classes: exact, out-of-scope, invalidated. Fail-closed handling of `Unknown`. |
| 13 | Tolerance carry-forward. LPTN sensitivity estimation script → `Tolerance` records with `source`. I3, I5, and I7 property tests. |
| 14 | **M3 demo + short write-up** (in `docs/log/`). Show a coolant change making the right claims stale and leaving the shaft claim alone. |

**M3 DoD:** a scripted demo runs in one command (`examples/motor_thermal/demo_change.ps1` / `.sh`). A short write-up of what the demo shows is in `docs/log/`.

## Phase 4 — Validity + planner (weeks 15–18)

| Week | Work |
|---|---|
| 15 | Integrate the existing `reval.uq` (conformal + AD, built in Phase 1) into the ML producers and verdicts. AD report in reasons. |
| 16 | Candidate generation. CP-SAT model (min cost + budgeted). Greedy + rerun-all planners. |
| 17 | `reval plan`, `reval run --plan` (job runner, append-only evidence). Re-assessment loop. I6 property test. Reports: JSON (canonical) → Markdown/HTML. Report hash (excludes `created_at` and `report_id`). Mandatory disclaimer. |
| 18 | **Buffer week** (absorbs Phase 1–4 overrun). Nothing new is scheduled. |

**M4 DoD:** `reval diff → plan → run → report` works end to end on the motor example. The planner is unit-tested against
brute force on small random instances (exact optimum match, solver status `OPTIMAL`).

## Phase 5 — ReValBench (weeks 19–23)

| Week | Work |
|---|---|
| 19 | Scenario generator for T1–T6, T10, T11 (Tier A). Producer result cache keyed by (producer code hash, input hash). |
| 20 | Virtual world model (calibrated on train + reserve only). T6–T9, T12 (Tier B). Truth oracles. Tier B ML retrained on world trajectories. Bootstrap statistics, ablation plumbing (A1–A8), cost-sensitivity and RQ4 (2×2) harness. |
| 21 | Baselines B0–B4. Metric computation. **Pilot on development seeds** (runtime, instance counts, ε, δ). **Pre-registration committed at the end of week 21.** |
| 22 | Final runs on fresh seeds: main comparison, ablations A1–A8, cost sensitivity, RQ4. |
| 23 | Analysis notebooks → figures and tables (scripted, regenerable). |

**M5 DoD:** `python -m bench.run --config bench/configs/full.yaml` regenerates every figure and table in the paper from scratch.
Results are archived with hashes.

## Phase 6 — Workspace + integration (weeks 24–27; starts only after the M5 DoD)

If M5 isn't met by week 23, the default UI scope is the **static HTML report** (`reval report --html`, cut line 5), and the time goes to finishing Phase 5.

| Week | Work |
|---|---|
| 24 | **Buffer week** (absorbs Phase 5 overrun). Then: FastAPI endpoints over the services ([09](09-api-and-ui.md)), single project (`p = "default"`). OpenAPI → generated TS client (`reval api-schema`). Alembic migrations (`reval db upgrade`). |
| 25 | Web UI: claim board, claim detail (justification tree, envelope plot), change timeline. |
| 26 | Graph explorer (`@xyflow/react`). Planner page with budget slider. GitHub Action (`reval diff --format markdown` on PR → comment). |
| 27 | Docker Compose (API + UI; PostgreSQL only if time allows). Usability check (RQ5) if you're doing it. Fix the top 5 issues. |

**M6 DoD:** the workspace runs locally on the motor example (`reval serve`, or `docker compose up`). The demo PR in the repo shows the action's comment.

## Phase 7 — Write-up and release (weeks 28–30)

| Week | Work |
|---|---|
| 28 | Paper draft ([research/paper-outline.md](research/paper-outline.md)). The README and docs site reuse the paper sections. Docs site (MkDocs Material): quickstart, concepts, motor tutorial, "add ReVal to your project" (`reval init`). |
| 29 | `pip install` from a wheel. 5-minute demo video. Tag `v1.0.0`. Optional: arXiv preprint or workshop submission, blog post / talk slides. |
| 30 | Buffer. Public release announcement. |

## Weekly rhythm

- **Monday:** pick the week's issues from the milestone. **Friday:** a 5-line log in `docs/log/YYYY-Www.md` (done / blocked / next / numbers / risks).
- **Every 2 weeks: self-review.** Demo something that runs (not slides) to yourself or anyone willing, update `docs/08-risks.md`, and
  apply cut lines early if behind.
- **Optional external feedback:** share the preprint, a demo video, or the repo with a practitioner or researcher, and log what they said.
- Every result number in a report is produced by a committed script. No hand-copied numbers.

## Cut lines (what to drop, in order, if behind schedule)

1. The TNN model (M4), the sequential planner, the second domain (stretch goals: drop first)
2. PostgreSQL support (keep SQLite only)
3. RQ5 usability study → replace with a heuristic walkthrough
4. GitHub Action and Docker Compose → keep the CLI only
5. Web UI → reduce to a static HTML report viewer, generated by `reval report --html`
6. Tier B → reduce to T7/T8 only (RQ4 then reports Tier A coverage evidence only)

**Never cut:** the deterministic core, fail-closed semantics, Tier A benchmark, baselines B0/B1/B2, pre-registration, reproducibility.

## Short (16-week) variant

| Weeks | Scope |
|---|---|
| 1–2 | Phase 0 |
| 3–5 | Phase 1 with M1 only, a 2-node LPTN, no optimizer O3 |
| 6–8 | Phase 2 |
| 9–10 | Phase 3 without tolerance carry-forward (exact and out-of-scope freshness only) |
| 11–12 | Phase 4 with the CP-SAT min-cost planner only |
| 13–14 | Tier A benchmark, B0–B2, ablations A1/A3/A6 |
| 15–16 | Static HTML report, write-up, demo |

In this variant, tolerance carry-forward becomes "future work". The research question narrows to field- and scope-level invalidation.
