# AGENTS.md

Instructions for AI coding agents (Codex, Claude Code, Copilot, …) and human contributors working in this repository.
Read this file fully before making changes.

## What this project is

**ReVal** is a continuous validation engine for engineering decisions. Given a change to an engineering project (data, model,
parameters, assumptions, requirements, code), it determines which engineering **claims** are still supported by fresh evidence,
which are stale, inconclusive, or violated, and the minimum-cost set of tests that restores support.

Reference domain: thermal validation of a permanent-magnet synchronous motor (Paderborn *Electric Motor Temperature* dataset).
This is a capstone project with a research component, so correctness, reproducibility, and honest reporting matter more than features.

Read these before non-trivial work:
- `docs/00-vision.md`: scope and non-goals
- `docs/03-domain-model.md`: **the contract** for entities, statuses, freshness, and invariants
- `docs/04-algorithms.md`: formal definitions of the engines
- `docs/07-roadmap.md`: the current phase and its Definition of Done

## Repository map

```
src/reval/core/        pure engines (graph, impact, validity, planner, status). NO I/O.
src/reval/domain/      frozen Pydantic models
src/reval/manifest/    reval.yaml schema + loader (pint units)
src/reval/hashing/     artifact hashers
src/reval/sdk/         @reval.producer decorator, Context
src/reval/store/       SQLAlchemy + Alembic (SQLite default, PostgreSQL optional)
src/reval/gitio/       snapshots at git revisions
src/reval/services/    application services
src/reval/api/         FastAPI
src/reval/cli/         Typer CLI (entry point `reval`)
src/reval/report/      report rendering
examples/motor_thermal/  reference engineering project (its own reval.yaml)
bench/                 ReValBench: scenarios, oracles, baselines, analysis
web/                   Vite + React + TypeScript UI
tests/                 unit/ property/ integration/ golden/
docs/                  plan, ADRs, research notes
```

## Commands

Python ≥ 3.12. Use [uv](https://docs.astral.sh/uv/) (`pip install -e ".[dev]"` in a venv also works).

```bash
uv sync --all-extras                 # install
uv run pytest                        # all tests
uv run pytest tests/property -x      # invariants only
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run reval --help
```

Web (once `web/` exists): `npm --prefix web ci`, `npm --prefix web run dev`, `npm --prefix web test`.

Before declaring a task done, run: `ruff check`, `ruff format --check`, `mypy src`, `pytest`. All of them must pass.

## Non-negotiable rules

1. **The core is deterministic and pure.** `src/reval/core/` must not do file/network I/O, read clocks, use unseeded randomness,
   or call any LLM or remote service. Inputs and outputs are immutable domain objects. Solvers run with fixed seeds and a single worker.
2. **No LLM ever decides a status.** Language models may only draft metadata for human review or paraphrase a finished report,
   behind an explicit feature flag, outside `core/`.
3. **Fail closed.** Unknown change kinds, undeclared dependencies, missing tolerances, and `selector="*"` on a changed artifact all
   **invalidate** evidence. Never add a code path that defaults to "still fresh".
4. **The domain-model doc is the contract.** If you change statuses, freshness rules, verdict rules, or invariants, update
   `docs/03-domain-model.md` in the same change and add or adjust property tests in `tests/property/`.
5. **Evidence and assessments are append-only.** Never update or delete them in place. New information means new records.
6. **Never split motor data by random rows.** Splits are by `profile_id` and are defined in `examples/motor_thermal/splits.yaml`.
   Calibration and test profiles must never be used for fitting.
7. **Units are explicit.** Every quantity carries a unit at the manifest/SDK boundary (`pint`). Temperatures are stored in °C as
   absolute values. Temperature *differences* (margins, tolerances, intervals) are in K. Don't mix them.
8. **No raw data or large binaries in git.** `data/`, `models/`, `.reval/`, and benchmark outputs are git-ignored. Data is fetched by scripts.
   Never commit or log credentials (for example, a Kaggle API token).
9. **Honest language.** Code, docs, UI copy, and reports must never say a design is "safe", "certified", or "verified to standard X".
   Use "supported by recorded evidence against the declared requirement". Every report includes the disclaimer.
10. **Every reported number comes from a committed script.** No hand-edited result tables.

## Coding conventions

- Python: type hints everywhere (`mypy --strict` on `core/` and `domain/`). Pydantic v2 `frozen=True` models for domain objects.
  Small pure functions in `core/`. Services orchestrate. Adapters do I/O.
- Naming follows the domain model exactly: `Claim`, `Evidence`, `Assessment`, `Status.SUPPORTED`, … Don't invent synonyms.
- Reasons are emitted as `Reason(code=ReasonCode.X, ...)`. Add new codes to the enum and to `docs/03-domain-model.md`.
- Tests: unit tests next to features in `tests/unit/`, invariants with Hypothesis in `tests/property/`, CLI/API flows in
  `tests/integration/`, report snapshots in `tests/golden/` (update them deliberately, never blindly).
- Comments explain *why*, not what. Docstrings on public functions.
- Frontend: TypeScript strict, a generated API client (never hand-written fetch types), no status signaled by color alone.

## Git workflow

- `main` is always green. Work on short branches: `feat/…`, `fix/…`, `docs/…`, `bench/…`, `exp/…`.
- [Conventional Commits](https://www.conventionalcommits.org/): `feat(core): tolerance carry-forward`, `fix(manifest): …`, `docs: …`, `bench: …`.
- One logical change per commit. Reference the milestone or issue (`M3`, `#12`) when one exists.
- Experiments that produce results: commit the config and the script, record the result hash in `docs/log/`. Don't commit large outputs.

## Definition of done (any task)

- Behavior matches `docs/03-domain-model.md` / `docs/04-algorithms.md`.
- Tests added or updated, including a property test if an invariant is involved. All checks pass.
- Docs updated if user-visible behavior, the CLI, the API, or semantics changed.
- No new rule violations from the list above.

## When unsure

Prefer the conservative, fail-closed, simpler option. Write the open question into the PR description or `docs/log/` rather than
guessing at engineering semantics.

## Working with Claude Code / Sonnet

- **Backlog:** `docs/tasks/BACKLOG.md` (status per task). Specs live in `docs/tasks/phase-*.md`. Binding signatures are in `docs/10-interfaces.md`.
- **Skills:** `/next-task` implements exactly one ready task end to end (branch → tests → code → checks → review → commit, never push).
  `/phase-refine` (run by Opus at each phase start) tightens specs against the real code.
- **Subagents:** `reval-reviewer` reviews a diff against these rules, the invariants, and the interfaces. `spec-checker` runs a task's acceptance criteria.
- **Ambiguity:** don't guess. Append to `docs/log/questions.md` and mark the task `blocked`.
- **Environment (Windows):** the venv is at `.venv`. Run tools as `.venv/Scripts/python -m pytest`, `.venv/Scripts/python -m ruff check .`,
  `.venv/Scripts/python -m mypy src`, `.venv/Scripts/reval`.
