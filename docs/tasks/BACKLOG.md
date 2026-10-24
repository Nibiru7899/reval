# Task backlog

This is the single index of work. Each task links to its full spec in a phase file.

## How to pick the next task
1. Take the **lowest ID** whose status is `todo` and whose **depends-on** tasks are all `done`. Skip tasks owned by `human` (those are for the user).
2. Set it to `in-progress` in this table (one task in progress at a time per agent).
3. Read the task's "read first" docs, implement exactly the spec, and run its acceptance commands plus the standard checks in `AGENTS.md`.
4. Set it to `review` (if owner is `sonnet+human-review`) or `done`. Commit using the Conventional Commits format with the task ID, e.g. `feat(core): P4-06 CP-SAT min-cost planner`.
5. If the spec is ambiguous or conflicts with `docs/03`/`docs/04`/`docs/10`, set the task to `blocked`, write the question in `docs/log/questions.md`, and stop. Don't guess at engineering semantics.

**Status values:** `todo` · `in-progress` · `review` · `done` · `blocked`

**Owners:** `sonnet` (a coding agent can do it alone) · `sonnet+human-review` (the agent implements, the user checks the result) · `human` (the user does it: decisions, supervisor contact, data access, studies, writing).

**Phase refinement:** at the start of each phase, run one Opus pass ("refine phase N tasks against the current code") to update specs with what the earlier phases actually built. Specs for later phases were written before the code existed.

## Phase 0 — Foundations ([phase-0-foundations.md](phase-0-foundations.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P0-01 | Tooling follow-up in `pyproject.toml` | sonnet | — | todo |
| P0-02 | Repo hygiene: issue/PR templates, backlog ticking, questions log | sonnet | — | todo |
| P0-03 | Dataset access (Kaggle token) and raw download | human | — | todo |
| P0-04 | Prior-art review | human (sonnet can assist) | — | todo |
| P0-05 | EDA notebook (after P1-01) | sonnet+human-review | P1-01 | todo |
| P0-06 | Choose declared limits and fix splits | human (sonnet drafts a proposal from EDA numbers) | P0-05, P1-02 | todo |
| P0-07 | Proposal and supervisor checkpoint | human | P0-04, P0-06 | todo |

## Phase 1 — Motor domain ([phase-1-motor.md](phase-1-motor.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P1-01 | Download, validate, convert to parquet | sonnet | P0-01 | todo |
| P1-02 | Profile-level splits | sonnet+human-review | P1-01 | todo |
| P1-03 | Feature engineering (derived + EWMA) | sonnet | P1-01 | todo |
| P1-04 | Trajectory models M1–M3 + peak evaluation harness | sonnet | P1-02, P1-03 | todo |
| P1-05 | Split-conformal peak intervals (`reval.uq.conformal`) | sonnet | P1-04 | todo |
| P1-06 | Applicability domain (`reval.uq.domain`) | sonnet | P1-03 | todo |
| P1-07 | 4-node LPTN simulator | sonnet | P1-03 | todo |
| P1-08 | LPTN identification + model-form band | sonnet | P1-07, P1-02 | todo |
| P1-09 | Drive map | sonnet | P1-03 | todo |
| P1-10 | Duty-cycle generator + subject library | sonnet | P1-09 | todo |
| P1-11 | Design optimizer O1/O2/O3 | sonnet | P1-05, P1-06, P1-09, P1-10 | todo |
| P1-12 | M1 milestone reproduction script | sonnet | P1-01…P1-11 | todo |

## Phase 2 — Core engine ([phase-2-core.md](phase-2-core.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P2-01 | Domain base, quantities, canonical JSON, hashing utilities | sonnet | P0-01 | todo |
| P2-02 | Domain entities: artifacts, engineering, evidence, policies | sonnet | P2-01 | todo |
| P2-03 | Snapshot, changes, assessment, plan models | sonnet | P2-02 | todo |
| P2-04 | Hashers (`reval.hashing`) | sonnet | P2-03, P0-01 | todo |
| P2-05 | Manifest schema + loader with units | sonnet | P2-03 | todo |
| P2-06 | Producer SDK + registry + runner | sonnet | P2-04, P2-05 | todo |
| P2-07 | Evidence graph (E1) | sonnet | P2-03 | todo |
| P2-08 | Verdicts (E3 part 1) | sonnet | P2-02 | todo |
| P2-09 | Claim status (E3 part 2) + `assess_all` | sonnet | P2-07, P2-08 | todo |
| P2-10 | SQL store (document tables) | sonnet | P2-03, P0-01 | todo |
| P2-11 | Project service + `reval status` / `reval snapshot` | sonnet | P2-04…P2-10 | todo |
| P2-12 | Property tests I1, I2, I4, I7 | sonnet | P2-09, P2-11 | todo |
| P2-13 | Motor manifest wiring | sonnet+human-review | P2-11, P1-12 | todo |

## Phase 3 — Change impact ([phase-3-impact.md](phase-3-impact.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P3-01 | Snapshot diff → `ChangeSet` | sonnet | P2-03, P2-04 | todo |
| P3-02 | Git lock reader + `reval diff` | sonnet | P3-01, P2-11 | todo |
| P3-03 | Freshness: exact + invalidated (fail-closed skeleton) | sonnet | P3-01, P2-07 | todo |
| P3-04 | Freshness: out-of-scope rows | sonnet | P3-03 | todo |
| P3-05 | Tolerance carry-forward | sonnet | P3-03 | todo |
| P3-06 | Wire freshness into `Project.assess` + I3 property test | sonnet | P3-03…P3-05 | todo |
| P3-07 | LPTN sensitivity estimation → tolerances | sonnet+human-review | P3-05, P1-08 | todo |
| P3-08 | Interim demo script | sonnet | P3-02, P3-06, P3-07, P2-13 | todo |

## Phase 4 — Validity + planner ([phase-4-validity-planner.md](phase-4-validity-planner.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P4-01 | Split-conformal utilities | sonnet | P2 done | todo |
| P4-02 | Applicability domain | sonnet | P4-01 | todo |
| P4-03 | Motor ML producers emit conformal + AD evidence | sonnet | P4-02, P1, P2 | todo |
| P4-04 | Verdicts/status AD + conformal tests | sonnet | P4-03 | todo |
| P4-05 | Obligations & candidate generation | sonnet | P4-04 | todo |
| P4-06 | CP-SAT min-cost planner | sonnet | P4-05 | todo |
| P4-07 | Budgeted variant | sonnet | P4-06 | todo |
| P4-08 | Greedy and "all" planners | sonnet | P4-06 | todo |
| P4-09 | `reval plan` CLI | sonnet | P4-08, P3 | todo |
| P4-10 | Job runner + `reval run` | sonnet | P4-09 | todo |
| P4-11 | Re-assessment loop + invariant I6 | sonnet | P4-10 | todo |
| P4-12 | Canonical report JSON | sonnet | P4-11 | todo |
| P4-13 | Markdown/HTML rendering, `reval report` | sonnet | P4-12 | todo |
| P4-14 | `reval explain` | sonnet | P4-12 | todo |
| P4-15 | M4 demo script + review | sonnet+human-review | P4-13, P4-14 | todo |

## Phase 5 — ReValBench ([phase-5-bench.md](phase-5-bench.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P5-01 | Pre-registration (**gate**) | human | P4-15 | todo |
| P5-02 | Bench harness: throwaway clones + commits | sonnet | P4-15 | todo |
| P5-03 | Scenario generator, Tier A T1–T5 | sonnet | P5-02 | todo |
| P5-04 | Tier A T6, T10, T11 | sonnet | P5-03 | todo |
| P5-05 | Tier B virtual world model | sonnet+human-review | P1 | todo |
| P5-06 | Tier B T6-B, T7, T8, T9, T12 | sonnet | P5-05, P5-04 | todo |
| P5-07 | Evidence oracle (B0) | sonnet | P5-02 | todo |
| P5-08 | Truth oracles | sonnet | P5-05 | todo |
| P5-09 | Baselines B1–B4 | sonnet | P5-07 | todo |
| P5-10 | Metrics | sonnet | P5-07, P5-08, P5-09 | todo |
| P5-11 | Runner, cache, smoke config | sonnet | P5-10 | todo |
| P5-12 | Cluster bootstrap + non-inferiority | sonnet | P5-10 | todo |
| P5-13 | Ablations A1–A7 | sonnet | P5-11 | todo |
| P5-14 | Cost sensitivity | sonnet | P5-11 | todo |
| P5-15 | Figures and tables | sonnet | P5-12, P5-13, P5-14 | todo |
| P5-16 | Full run + archive | sonnet+human-review | P5-01, P5-15 | todo |

## Phase 6 — Workspace ([phase-6-workspace.md](phase-6-workspace.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P6-01 | FastAPI app skeleton | sonnet | P4-15 | todo |
| P6-02 | Read endpoints | sonnet | P6-01 | todo |
| P6-03 | Plans, jobs, SSE | sonnet | P6-02 | todo |
| P6-04 | Report endpoints | sonnet | P6-02, P4-13 | todo |
| P6-05 | Alembic + PostgreSQL | sonnet | P6-01 | todo |
| P6-06 | Web scaffold + generated client | sonnet | P6-02 | todo |
| P6-07 | Claim board | sonnet | P6-06 | todo |
| P6-08 | Claim detail + envelope plot | sonnet | P6-07 | todo |
| P6-09 | Change timeline | sonnet | P6-06 | todo |
| P6-10 | Graph explorer | sonnet | P6-06 | todo |
| P6-11 | Planner page | sonnet | P6-03, P6-06 | todo |
| P6-12 | Report view | sonnet | P6-04 | todo |
| P6-13 | GitHub Action | sonnet | P4-15 | todo |
| P6-14 | Docker Compose | sonnet | P6-05, P6-06 | todo |
| P6-15 | Usability check (optional) | human | P6-11 | todo |

## Phase 7 — Release ([phase-7-release.md](phase-7-release.md))

| ID | Title | Owner | Depends on | Status |
|---|---|---|---|---|
| P7-01 | Paper draft | human | P5-16 | todo |
| P7-02 | Documentation site | sonnet | P4-15 | todo |
| P7-03 | Tutorial + second toy domain | sonnet+human-review | P7-02 | todo |
| P7-04 | Packaging + install test | sonnet | P7-02 | todo |
| P7-05 | End-to-end reproduction script | sonnet | P5-16 | todo |
| P7-06 | Poster, video, slides | human | P7-01 | todo |
| P7-07 | Release v1.0.0 | sonnet+human-review | P7-04, P7-05 | todo |
| P7-08 | arXiv / submission | human | P7-01 | todo |
