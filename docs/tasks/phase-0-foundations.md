# Phase 0 — Foundations (roadmap weeks 1–2)

Conventions for every task file:
- **Owner:** `sonnet` = an AI coding agent does it end to end. `human` = only the student can do it (accounts, approvals, judgment calls).
  `sonnet+human-review` = the agent drafts and the student approves before merge.
- **Done** = every acceptance criterion holds, `ruff check . && ruff format --check . && mypy src && pytest` passes, and the task's
  row in `docs/tasks/BACKLOG.md` is ticked. One task = one branch = one PR/merge. Conventional Commit messages.
- If the spec is ambiguous, **don't guess engineering semantics**. Append the question to `docs/log/questions.md` and stop or pick the fail-closed option.

---

## P0-01 — Tooling follow-up in `pyproject.toml`
- **Owner:** sonnet · **Depends on:** — · **Read first:** `AGENTS.md`, ADR 0003, ADR 0005
- **Files:** `pyproject.toml`, `tests/conftest.py` (new), `.github/workflows/ci.yml`
- **Spec:** (already done during planning: `sqlalchemy` and `rich` in main deps, `pythonpath`, and the `data` marker. Verify them and do the rest.)
  1. Check that `sqlalchemy>=2.0` is in `[project].dependencies` and that `alembic` stays in `server`.
  2. Add `pandas>=2.2` and `pyarrow>=16` to the main dependencies (the dataframe hasher needs them). Keep `scikit-learn`, `matplotlib`, and `joblib` in `motor`.
  3. `[tool.pytest.ini_options]`: check `pythonpath = ["src", "examples/motor_thermal"]`. Add a `"slow: > 10 s"` marker next to the existing `data` marker.
  4. `tests/conftest.py`: an autouse-free helper. Register a collection hook that skips `@pytest.mark.data` tests when
     `examples/motor_thermal/data/processed/measures.parquet` doesn't exist (message: "motor dataset not downloaded; see P1-01").
  5. CI: install with `.[dev,motor]`. Add `-m "not data"` to pytest.
- **Acceptance:** `pip install -e ".[dev,motor]"` works. `pytest -m "not data"` passes. A dummy `@pytest.mark.data` test is reported as skipped
  (add it to `tests/unit/test_markers.py`; it asserts `True`).
- **Out of scope:** uv lock files, Alembic.
- **Pitfalls:** don't put `examples/motor_thermal` into the wheel. Use `pythonpath` only.

## P0-02 — Repo hygiene: issue/PR templates, backlog ticking, questions log
- **Owner:** sonnet · **Depends on:** — · **Read first:** `AGENTS.md` (Git workflow)
- **Files:** `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/task.md`, `docs/log/questions.md`
- **Spec:** the PR template has these checkboxes: task id, linked docs sections, tests added, invariants touched (I1–I7), docs updated, checks pass,
  no AGENTS.md rule violated. The issue template mirrors the task-spec headings in this file. `questions.md` starts with a header
  and a table: `date | task | question | proposed answer | resolved by | resolution`.
- **Acceptance:** the files exist and the Markdown renders (no lint tool needed).

## P0-03 — Dataset access (Kaggle token) and raw download
- **Owner:** human · **Depends on:** — · **Read first:** `docs/05-motor-domain.md` §1
- **Steps (student):**
  1. Read the dataset page and its **license** (`kaggle.com/datasets/wkirgsn/electric-motor-temperature`). Write the license name and the date checked into `docs/log/questions.md` as a resolved entry.
  2. Create your own Kaggle API token and place it where the Kaggle CLI expects it (`%USERPROFILE%\.kaggle\kaggle.json`). **Never commit it. Never paste it into a chat or an agent prompt.**
  3. After P1-01 exists, run `python examples/motor_thermal/scripts/download_data.py`. Or download the zip manually into `examples/motor_thermal/data/raw/`.
- **Acceptance:** `examples/motor_thermal/data/raw/measures_v2.csv` (or the file name the dataset actually ships) exists locally and is git-ignored (`git status` clean).

## P0-04 — Prior-art review
- **Owner:** human (sonnet can assist with web search and summarizing; the student verifies every citation against the primary source)
- **Depends on:** — · **Read first:** `docs/01-problem-and-prior-art.md` §2, §4
- **Files:** `docs/research/related-work.csv`, `docs/research/prior-art-summary.md` (new)
- **Steps:** run the search strings in §4. Fill ≥ 25 rows of `related-work.csv` (`verified=yes` only once you've read the primary source).
  Resolve every ⚠️ item in §2.9 (found → cite exactly; not found → delete it from docs/01). Write a one-page summary with the
  closest three works and how ReVal differs. Apply the **kill criterion**.
- **Agent assist prompt (optional):** "Search for X. For each candidate give title, authors, year, venue, DOI/URL, and a 2-sentence
  summary. Mark anything you couldn't open as unverified." The agent must not mark rows verified.
- **Acceptance:** ≥ 25 rows. Zero ⚠️ left in docs/01. The summary is reviewed by the supervisor (P0-07).

## P0-05 — EDA notebook (after P1-01)
- **Owner:** sonnet+human-review · **Depends on:** P1-01 · **Read first:** `docs/05-motor-domain.md` §1–2, §6
- **Files:** `examples/motor_thermal/notebooks/01_eda.ipynb` (outputs cleared before commit), `examples/motor_thermal/motor/eda.py` (reusable functions)
- **Spec:** functions in `motor/eda.py` (tested with a synthetic frame):
  - `profile_summary(df) -> pd.DataFrame` with one row per `profile_id`: n_rows, duration_h (rows / 2 / 3600), min/max for coolant, ambient, motor_speed, torque, and max for pm and stator_winding.
  - `peak_distribution(df, target, window_s) -> pd.Series` of per-window peaks over non-overlapping windows.
  - The notebook only calls these functions and plots: profile durations, operating-region scatter (speed × torque colored by coolant), peak histograms for pm and stator_winding at windows of 10, 30, and 60 min.
- **Acceptance:** `tests/unit/motor/test_eda.py` passes on a synthetic 2-profile frame. The notebook runs top to bottom on real data (human check).
- **Pitfalls:** sampling is 2 Hz (window_s × 2 rows). Never treat rows across profile boundaries as contiguous.

## P0-06 — Choose declared limits and fix splits
- **Owner:** human (sonnet drafts a proposal from EDA numbers) · **Depends on:** P0-05, P1-02
- **Files:** `examples/motor_thermal/params/limits.yaml`, `examples/motor_thermal/splits.yaml` (generated by P1-02, reviewed here)
- **Spec:** set `pm_peak_limit_degC` and `sw_peak_limit_degC` at about the 90th–95th percentile of 30-min window peaks over `train` profiles
  (rounded to 5 °C). Add a comment header: "Study parameters, not manufacturer ratings." Also set `inverter_current_limit_A`
  (the 99th percentile of `i_s` over train) and `shaft_d_limit_mm: 30.05`.
- **Acceptance:** `limits.yaml` is committed with the comment header. The decision and percentile numbers are recorded in `docs/log/`.

## P0-07 — Proposal and supervisor checkpoint
- **Owner:** human · **Depends on:** P0-04, P0-06
- **Deliverable:** a 2–3 page proposal built from `docs/00`, `docs/01` §1/§3, and `docs/06` §1. Get supervisor sign-off on scope, the
  kill-criterion outcome, and the 30- or 16-week variant from `docs/07-roadmap.md`.
- **Acceptance:** the decision is recorded in `docs/log/` (variant chosen, any scope changes). Update `docs/07-roadmap.md` if the variant changes.
