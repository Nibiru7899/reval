# Task backlog

This is the single index of work. Each task links to its full spec in a phase file. **This table is generated** from the phase files by
the check script (see the bottom). Edit the phase files, never the ID, title, owner, or dependency columns here. Only the **Status** column is edited by hand or by agents.

## How to pick the next task
1. Take the **lowest ID** (phase, then number) whose status is `todo`, whose owner is `sonnet` or `sonnet+human-review`, and whose dependencies are all
   `done` **or** `review`. Agents never pick `human` tasks (those are for the owner).
2. Set it to `in-progress` (one task in progress at a time per agent).
3. Read the task's "Read first" docs plus the `docs/10-interfaces.md` sections it names. Implement exactly the spec, then run its acceptance commands and the standard checks in `AGENTS.md`.
4. Set it to `review` (owner `sonnet+human-review`, or any task with a `NEEDS HUMAN` item) or `done`. Commit using Conventional Commits with the task ID, e.g. `feat(core): P4-06 CP-SAT min-cost planner`.
5. **Merging (decision D26):** once every check passes and the reviewer has no open blocker or major finding, the agent fast-forward-merges
   its own branch into `main` locally (`git switch main && git merge --ff-only <branch>`), so the next task builds on it. If `--ff-only`
   fails it stops and reports. Agents never rebase, force, create merge commits, or `git push`. `sonnet+human-review` tasks are merged
   with status `review`, and the user checks them later.
6. If the spec is ambiguous or conflicts with `docs/03` / `docs/04` / `docs/10`, set the task to `blocked`, add a `Q-NNN` entry to `docs/log/questions.md` (keep its template), and stop. Don't guess at engineering semantics.

**Status values:** `todo` · `in-progress` · `review` · `done` · `blocked`

**Owners:** `sonnet` (a coding agent does it alone) · `sonnet+human-review` (the agent implements, the owner checks the result) · `human` (the owner: decisions, sign-offs, studies, writing).

**Phase refinement:** at the start of each phase, run one Opus pass (`/phase-refine`) to update that phase's specs with what earlier phases actually built.

**Cross-phase dependencies (justified):** `P0-05 → P1-01` and `P0-06 → P1-02` (EDA and limits need the prepared data and the splits); `P1-01 → P2-01` and `P1-06 → P2-01`
(`reval.errors` and `Frozen` are needed by motor and uq code; P2-01 is small and standalone). Every other dependency points to the same or an earlier phase.

## Phase 0 — Foundations ([phase-0-foundations.md](phase-0-foundations.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P0-01 | Tooling remainder: data-marker skip hook | sonnet | — | todo |
| P0-02 | Repo hygiene: PR and issue templates | sonnet | — | todo |
| P0-03 | Dataset license check and download (no token) | human | — | done |
| P0-04 | Prior-art review | human | — | todo |
| P0-05 | EDA functions and notebook | sonnet+human-review | P1-01 | todo |
| P0-06 | Choose declared limits | human | P0-05, P1-02 | todo |
| P0-07 | Scope checkpoint | human | P0-04 | todo |

## Phase 1 — Motor domain ([phase-1-motor.md](phase-1-motor.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P1-01 | Download, validate, convert to parquet | sonnet | P0-01, P2-01 | todo |
| P1-02 | Profile-level splits | sonnet+human-review | P1-01 | todo |
| P1-03 | Feature engineering (derived + EWMA) | sonnet | P1-01 | todo |
| P1-04 | Trajectory models M1–M3 + peak evaluation harness | sonnet | P1-02, P1-03 | todo |
| P1-05 | Split-conformal (`reval.uq.conformal`) + motor `PeakConformal` | sonnet | P1-04 | todo |
| P1-06 | Applicability domain (`reval.uq.domain`) | sonnet | P1-05, P2-01 | todo |
| P1-07 | 4-node LPTN simulator + cooling parameters | sonnet | P1-03 | todo |
| P1-08 | LPTN identification + model-form band | sonnet | P1-07, P1-02 | todo |
| P1-09 | Drive map | sonnet | P1-03, P1-06 | todo |
| P1-10 | Duty-cycle generator + subject library | sonnet | P1-02, P1-03 | todo |
| P1-11 | Design optimizer O1/O2/O3 | sonnet | P1-05, P1-06, P1-09, P1-10 | todo |
| P1-12 | M1 milestone reproduction script | sonnet | P0-03, P0-06, P1-01, P1-02, P1-03, P1-04, P1-05, P1-06, P1-07, P1-08, P1-09, P1-10, P1-11, P1-13 | todo |
| P1-13 | Calibration script: uq artifacts per model | sonnet | P1-05, P1-06 | todo |

## Phase 2 — Core engine ([phase-2-core.md](phase-2-core.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P2-01 | Domain base, intervals, canonical JSON, errors | sonnet | P0-01 | todo |
| P2-02 | Selectors, artifacts, engineering entities | sonnet | P2-01 | todo |
| P2-03 | Snapshot, changes, assessment, plan models + `core/selectors.py` | sonnet | P2-14 | todo |
| P2-04 | Hashers (`reval.hashing`) | sonnet | P2-03 | todo |
| P2-05 | Manifest schema + loader with units + fixture project | sonnet | P2-03 | todo |
| P2-06 | Producer SDK: decorator, registry, context, code hash | sonnet | P2-05 | todo |
| P2-07 | Evidence graph (E1) | sonnet | P2-15 | todo |
| P2-08 | Verdicts (E3 part 1) | sonnet | P2-03 | todo |
| P2-09 | Claim status (E3 part 2) + `assess_all` | sonnet | P2-08 | todo |
| P2-10 | SQL store (document tables) | sonnet | P2-03 | todo |
| P2-11 | Project service + lock file (no git) | sonnet | P2-09, P2-10, P2-15 | todo |
| P2-12 | Property tests I1, I2, I4 + core coverage gate | sonnet | P2-09, P2-11 | todo |
| P2-13 | Motor manifest wiring (non-ML producers) | sonnet+human-review | P0-06, P1-08, P1-09, P1-10, P2-18 | todo |
| P2-14 | Evidence, producers, policies | sonnet | P2-02 | todo |
| P2-15 | Producer runner | sonnet | P2-16 | todo |
| P2-16 | Snapshot builder | sonnet | P2-04, P2-05, P2-06 | todo |
| P2-17 | CLI: `snapshot` and `status` | sonnet | P2-11 | todo |
| P2-18 | CLI: `run --all` | sonnet | P2-17 | todo |

## Phase 3 — Change impact ([phase-3-impact.md](phase-3-impact.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P3-01 | Snapshot diff → `ChangeSet` | sonnet | P2-03, P2-16 | todo |
| P3-02 | Git lock reader + `reval diff` (change set only) | sonnet | P3-01, P2-17 | todo |
| P3-03 | Freshness: hard failures, exact, relevance, invalidation (fail-closed skeleton) | sonnet | P3-01, P2-15 | todo |
| P3-04 | Freshness: out-of-scope rows | sonnet | P3-03 | todo |
| P3-05 | Tolerance carry-forward + I5 | sonnet | P3-03 | todo |
| P3-06 | Wire freshness into `Project.assess` + `reval diff` claim section | sonnet | P3-02, P3-04, P3-05 | todo |
| P3-07 | LPTN sensitivity estimation → tolerances | sonnet+human-review | P3-05, P1-08, P2-13 | todo |
| P3-08 | Interim demo script | sonnet | P3-06, P3-07 | todo |
| P3-09 | `reval diff --format markdown` | sonnet | P3-06 | todo |
| P3-10 | Property tests I3 and I7 | sonnet | P3-06, P2-12 | todo |

## Phase 4 — Validity + planner ([phase-4-validity-planner.md](phase-4-validity-planner.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P4-01 | Extend `reval.uq.conformal`: `GroupedSplitConformal` | sonnet | P1-05 | todo |
| P4-02 | Extend `reval.uq.domain`: combine domain reports | sonnet | P1-06 | todo |
| P4-03 | Motor ML producers (conformal + AD evidence) | sonnet | P4-02, P1-13, P2-13 | todo |
| P4-04 | ML gate tests (verdicts and status) | sonnet | P2-09, P2-12 | todo |
| P4-05 | Planning problem: obligations, candidates, independence | sonnet | P2-09 | todo |
| P4-06 | CP-SAT min-cost planner | sonnet | P4-05 | todo |
| P4-07 | Budgeted variant (max-restored) + `deferred` | sonnet | P4-06 | todo |
| P4-08 | Greedy and "all" planners | sonnet | P4-06 | todo |
| P4-09 | `Project.plan` + `reval plan` | sonnet | P4-07, P4-08, P3-06 | todo |
| P4-10 | Job runner + `reval run --plan/--only` | sonnet | P4-09, P2-18 | todo |
| P4-11 | Re-assessment loop + invariant I6 | sonnet | P4-10 | todo |
| P4-12 | Canonical report JSON | sonnet | P4-11 | todo |
| P4-13 | Markdown + HTML rendering, `reval report` | sonnet | P4-12 | todo |
| P4-14 | `reval explain CLAIM` | sonnet | P4-12 | todo |
| P4-15 | M4 demo script + review | sonnet+human-review | P4-03, P4-13, P4-14, P3-08 | todo |
| P4-16 | `reval init` and `reval graph` | sonnet | P2-17, P2-07 | todo |

## Phase 5 — ReValBench ([phase-5-bench.md](phase-5-bench.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P5-01 | Pre-registration (HUMAN GATE) | human | P5-17 | todo |
| P5-02 | Bench harness: throwaway clones + scenario commits | sonnet | P3-06, P4-10 | todo |
| P5-03 | Scenario model + generator, Tier A part 1 (T1–T5) | sonnet | P5-02, P4-03 | todo |
| P5-04 | Tier A part 2 (T6, T10, T11) | sonnet | P5-03 | todo |
| P5-05 | Tier B virtual world model | sonnet+human-review | P1-08 | todo |
| P5-06 | Tier B scenarios (T6-B, T7, T8, T9, T12) | sonnet | P5-18, P5-04 | todo |
| P5-07 | Evidence oracle (B0 rerun-all) | sonnet | P5-02 | todo |
| P5-08 | Truth oracles | sonnet | P5-05, P5-07 | todo |
| P5-09 | Baselines B1–B4 | sonnet | P5-07 | todo |
| P5-10 | Metrics | sonnet | P5-07, P5-08, P5-09 | todo |
| P5-11 | Runner, cache, smoke config | sonnet | P5-10, P5-04, P5-06 | todo |
| P5-12 | Statistics: stratified cluster bootstrap + non-inferiority | sonnet | P5-10 | todo |
| P5-13 | Ablation settings plumbing (A1, A2, A3, A6, A7) | sonnet | P5-11 | todo |
| P5-14 | Cost sensitivity | sonnet | P5-11 | todo |
| P5-15 | Figures and tables (scripted) | sonnet | P5-12, P5-13, P5-19, P5-14, P5-20 | todo |
| P5-16 | Final run + archive (HUMAN REVIEW) | sonnet+human-review | P5-01, P5-15 | todo |
| P5-17 | Pilot run on development seeds | sonnet+human-review | P5-11, P5-12, P5-13, P5-19, P5-14, P5-20 | todo |
| P5-18 | Tier B base snapshots: ML retrained on world trajectories | sonnet | P5-05, P4-03 | todo |
| P5-19 | Uncertainty and AD ablations (A4, A5, A8) | sonnet | P5-13, P4-01 | todo |
| P5-20 | RQ4 optimizer experiment (Tier B, 2 × 2) | sonnet | P5-08, P5-18, P1-11 | todo |

## Phase 6 — Workspace + integration ([phase-6-workspace.md](phase-6-workspace.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P6-01 | FastAPI app skeleton + `reval serve` | sonnet | P4-15, P5-16 | todo |
| P6-02 | Read endpoints: projects, snapshots, claims, evidence, diff, graph | sonnet | P6-01 | todo |
| P6-03 | Plans, jobs, SSE | sonnet | P6-02 | todo |
| P6-04 | Report endpoints | sonnet | P6-02, P4-13 | todo |
| P6-05 | Alembic migrations, `reval db upgrade`, PostgreSQL CI | sonnet | P6-01 | todo |
| P6-06 | Web scaffold, generated client, `reval api-schema` | sonnet | P6-02 | todo |
| P6-07 | Claim board page | sonnet | P6-06 | todo |
| P6-08 | Claim detail: justification tree + envelope plot | sonnet | P6-07 | todo |
| P6-09 | Change timeline | sonnet | P6-06 | todo |
| P6-10 | Graph explorer | sonnet | P6-06 | todo |
| P6-11 | Planner page | sonnet | P6-03, P6-06 | todo |
| P6-12 | Report view | sonnet | P6-04, P6-06 | todo |
| P6-13 | GitHub Action | sonnet | P3-09 | todo |
| P6-14 | Docker Compose | sonnet | P6-06, P6-12 | todo |
| P6-15 | Usability check (RQ5, optional) | human | P6-11 | todo |

## Phase 7 — Write-up + release ([phase-7-release.md](phase-7-release.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P7-01 | Paper draft | human | P5-16 | todo |
| P7-02 | Documentation site | sonnet | P4-15 | todo |
| P7-03 | Tutorial: add ReVal to a new project | sonnet+human-review | P7-02, P4-16 | todo |
| P7-04 | Packaging + install test | sonnet | P7-02 | todo |
| P7-05 | End-to-end reproduction script | sonnet | P5-16 | todo |
| P7-06 | Demo video and talk slides (optional) | human | P7-01 | todo |
| P7-07 | Release v1.0.0 | sonnet+human-review | P7-04, P7-05 | todo |
| P7-08 | arXiv preprint / workshop submission (optional) | human | P7-01 | todo |

## Checking this file

The table was generated from the phase files and verified on 2026-10-26: no missing IDs, no unknown dependency IDs, no cycles, and no
dependency on a later phase other than the justified ones above. After editing a phase file's task header, re-run the same check
(parse every `## P<phase>-<n> — <title>` heading plus the `- **Owner:** … · **Depends on:** …` line that follows it).

Total: 107 tasks (88 sonnet, 10 sonnet+human-review, 9 human).
