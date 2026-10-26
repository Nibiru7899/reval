# Phase 0 — Foundations (roadmap weeks 1–2)

Conventions for every task file (phases 0–7):
- **Header line format** (parsed by the BACKLOG check script, keep it exact):
  `## <ID> — <Title>` followed by `- **Owner:** <owner> · **Depends on:** <IDs or —> · **Read first:** <docs>`.
- **Owner:** `sonnet` = an AI coding agent does it end to end. `sonnet+human-review` = the agent implements and the student checks the
  result (the agent marks the task `review`). `human` = only the student can do it (accounts, approvals, judgment calls). Agents never pick `human` tasks.
- **Dependencies** are explicit task IDs. A dependency counts as satisfied when its status is `review` or `done`.
- **Binding contract:** `docs/10-interfaces.md` for names, paths, and signatures. `docs/03-domain-model.md` for meaning. If a task text and `docs/10`
  disagree, `docs/10` wins. If `docs/10` and `docs/03` disagree, stop and log a question.
- **Done** = every acceptance criterion holds, and these all pass (Windows venv shown; elsewhere use `.venv/bin/python`):
  `.venv/Scripts/python -m ruff check .`, `.venv/Scripts/python -m ruff format --check .`, `.venv/Scripts/python -m mypy src`,
  `.venv/Scripts/python -m pytest`. Then update the task's status in `docs/tasks/BACKLOG.md`.
- **Git:** one task = one branch (`feat/<id>-<slug>`), Conventional Commits with the task ID. Never push. Until decision D26 is made, the
  **user** fast-forward-merges each finished branch into `main` before the next task starts.
- **Tests live under `tests/` only** (`tests/unit/…`, `tests/property/`, `tests/integration/`, `tests/golden/`, `tests/bench/`). pytest runs with
  `--import-mode=importlib` and `pythonpath = ["src", ".", "examples/motor_thermal"]`. `tests/unit/motor/` has **no** `__init__.py`.
- **`NEEDS HUMAN`** marks an acceptance item that only the student can judge. Every such item comes with a runnable check the agent does run.
- If the spec is ambiguous, **don't guess engineering semantics**. Append the question to `docs/log/questions.md` (keep its template), set the task to `blocked`, and stop.

---

## P0-01 — Tooling remainder: data-marker skip hook
- **Owner:** sonnet · **Depends on:** — · **Read first:** `AGENTS.md`, `pyproject.toml`, `.github/workflows/ci.yml`
- **Already done during planning (verify only, don't redo):** `sqlalchemy` and `rich` are main dependencies. `alembic` is in the `server` extra.
  pytest has `pythonpath = ["src", ".", "examples/motor_thermal"]`, `--import-mode=importlib`, and the `data` and `slow` markers. Ruff format
  excludes `*.md`. CI installs `.[dev,motor,server]`, checks out with `fetch-depth: 0`, and runs `pytest -m "not data and not slow"`.
- **Decision recorded here:** pandas and pyarrow stay in the `motor` extra (**not** main dependencies). The dataframe hasher lazy-imports pandas
  and raises `MissingExtraError("motor")` when it's missing (`docs/10` §6).
- **Files:** `tests/conftest.py` (new), `tests/unit/test_markers.py` (new)
- **Spec:**
  1. `tests/conftest.py`: a `pytest_collection_modifyitems` hook that adds a skip marker to every `@pytest.mark.data` item when
     `examples/motor_thermal/data/processed/measures.parquet` doesn't exist (reason: `"motor dataset not downloaded; see P0-03 / P1-01"`).
     Also define Hypothesis profiles `ci` (`max_examples=200`) and `thorough` (`max_examples=2000`), loading `ci` by default and
     `HYPOTHESIS_PROFILE` from the environment if set.
  2. `tests/unit/test_markers.py`: one test marked `data` that asserts `True`, and one unmarked test that asserts the hook's path constant is
     `examples/motor_thermal/data/processed/measures.parquet`.
- **Acceptance:** `.venv/Scripts/python -m pytest -rs tests/unit/test_markers.py` shows the data test as **skipped** with the reason above (data absent).
- **Out of scope:** uv lock files, Alembic, coverage thresholds (P2-12).
- **Pitfalls:** don't put `examples/motor_thermal` into the wheel. It's on the pytest path only.

## P0-02 — Repo hygiene: PR and issue templates
- **Owner:** sonnet · **Depends on:** — · **Read first:** `AGENTS.md` (Git workflow), `docs/log/questions.md`
- **Files:** `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/task.md`
- **Spec:** the PR template has checkboxes for: task ID, linked docs sections, tests added, invariants touched (I1–I7), docs updated, all four
  checks pass, and no AGENTS.md rule violated. The issue template mirrors the task header format of this file (Owner, Depends on, Read first,
  Files, Spec, Acceptance, Out of scope, Pitfalls). **Do not touch `docs/log/questions.md`.** Its `Q-NNN` template is used by the skills.
- **Acceptance:** `.venv/Scripts/python -c "import pathlib; t=pathlib.Path('.github/pull_request_template.md').read_text(); assert all(s in t for s in ['I1','AGENTS.md','Task'])"` exits 0.

## P0-03 — Dataset access (Kaggle token) and raw download
- **Owner:** human · **Depends on:** — · **Read first:** `docs/05-motor-domain.md` §1
- **Steps (student):**
  1. Confirm the dataset's **license** on its page (`kaggle.com/datasets/wkirgsn/electric-motor-temperature`; the plan records CC BY-SA 4.0, v3).
     Record the license and the date checked as a resolved entry in `docs/log/questions.md`.
  2. Create your own Kaggle API token and put it where the Kaggle CLI expects it (`%USERPROFILE%\.kaggle\kaggle.json`). **Never commit it.
     Never paste it into a chat or an agent prompt.**
  3. After P1-01 exists, run `.venv/Scripts/python examples/motor_thermal/scripts/download_data.py`, or download the zip by hand into
     `examples/motor_thermal/data/raw/`.
- **Acceptance:** exactly one CSV exists under `examples/motor_thermal/data/raw/`, and `git status --porcelain examples/motor_thermal/data` prints nothing (git-ignored).

## P0-04 — Prior-art review
- **Owner:** human (sonnet can assist with search and summaries; only the student marks rows verified) · **Depends on:** — · **Read first:** `docs/01-problem-and-prior-art.md` §2, §2.9, §4
- **Files:** `docs/research/related-work.csv`, `docs/research/prior-art-summary.md` (new)
- **Steps:** run the search strings in §4. Fill ≥ 25 rows of `related-work.csv`, with `verified=yes` only after reading the primary source.
  §2.9 already lists the outcomes for the five originally unverified items. Confirm the found ones (for example, the OpenModelica MDPI
  author list) against the primary source. Write a one-page summary covering the three closest works and how ReVal differs. Apply the **kill criterion**.
- **Agent assist prompt (optional):** "Search for X. For each candidate give title, authors, year, venue, DOI/URL, and a 2-sentence summary.
  Mark anything you couldn't open as unverified." The agent must never set `verified=yes`.
- **Acceptance:** `.venv/Scripts/python -c "import csv; r=list(csv.DictReader(open('docs/research/related-work.csv',encoding='utf-8'))); assert len(r)>=25"` exits 0.
  NEEDS HUMAN: the supervisor reviews the summary (P0-07).

## P0-05 — EDA functions and notebook
- **Owner:** sonnet+human-review · **Depends on:** P1-01 · **Read first:** `docs/05-motor-domain.md` §1–2, §6
- **Files:** `examples/motor_thermal/motor/eda.py`, `examples/motor_thermal/notebooks/01_eda.ipynb` (outputs cleared before commit), `tests/unit/motor/test_eda.py`
- **Spec:** functions in `motor/eda.py`:
  - `profile_summary(df: pd.DataFrame) -> pd.DataFrame`: one row per `profile_id` with `n_rows`, `duration_h` (rows / 2 / 3600), min and max of
    `coolant`, `ambient`, `motor_speed`, `torque`, and max of `pm` and `stator_winding`.
  - `peak_distribution(df: pd.DataFrame, target: str, window_s: float) -> pd.Series`: per-window peaks over non-overlapping windows **within each
    profile** (window rows = `window_s * 2`; the trailing partial window is dropped).
  - The notebook only calls these functions and plots: profile durations; an operating-region scatter (speed × torque, colored by coolant);
    peak histograms for `pm` and `stator_winding` at 10, 30, and 60 min windows. It also prints the profile count (expected ≈ 69; assert nothing).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_eda.py` passes on a synthetic 2-profile frame (windows never span profiles).
  NEEDS HUMAN: the notebook runs top to bottom on real data.
- **Pitfalls:** sampling is 2 Hz. `torque` and `motor_speed` are **estimates** derived from currents and voltages, not sensor readings. Say so in the notebook.

## P0-06 — Choose declared limits
- **Owner:** human (sonnet drafts a proposal from EDA numbers) · **Depends on:** P0-05, P1-02 · **Read first:** `docs/05-motor-domain.md` §6
- **Files:** `examples/motor_thermal/params/limits.yaml`, `docs/log/<date>-limits.md`
- **Spec:** set `pm_peak_limit_degC` and `sw_peak_limit_degC` at about the 90th–95th percentile of 30-min window peaks over **train** profiles
  (from `splits.yaml`), rounded to 5 °C. Also set `inverter_current_limit_A` (the 99th percentile of `i_s` over train) and `shaft_d_limit_mm: 30.05`.
  Comment header: "Study parameters, not manufacturer ratings."
- **Acceptance:** `.venv/Scripts/python -c "import yaml; d=yaml.safe_load(open('examples/motor_thermal/params/limits.yaml')); assert {'pm_peak_limit_degC','sw_peak_limit_degC','inverter_current_limit_A','shaft_d_limit_mm'} <= set(d)"` exits 0.
  The percentile numbers and the decision are recorded in `docs/log/`.

## P0-07 — Proposal and supervisor checkpoint
- **Owner:** human · **Depends on:** P0-04 · **Read first:** `docs/00-vision.md`, `docs/01` §1/§3, `docs/06` §1, `docs/07-roadmap.md`
- **Deliverable:** a 2–3 page proposal. Get supervisor sign-off on the scope, the kill-criterion outcome, and the 30- or 16-week variant.
- **Acceptance:** the decision (variant chosen, any scope changes) is recorded in `docs/log/`. `docs/07-roadmap.md` is updated if the variant changes.
