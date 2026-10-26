# Phase 7 — Write-up and release (roadmap weeks 28–30)

**Read first:** `AGENTS.md` (rule 9: honest language; rule 10: numbers come from scripts), `docs/research/paper-outline.md`, `docs/06-evaluation.md` §7.
Conventions: see the header of `phase-0-foundations.md`.

---

## P7-01 — Paper draft
- **Owner:** human (sonnet assists only with LaTeX scaffolding and figure inclusion) · **Depends on:** P5-16 · **Read first:** `docs/research/paper-outline.md`
- **Files:** `paper/` (LaTeX, with an IEEE or ACM template for the target venue), `paper/figures/` (copied by script from `bench/results/<hash>/figures`), `paper/check_numbers.py`
- **Spec:** follow `paper-outline.md`. Every number is pulled in via `\input` from the generated `bench/results/<hash>/tables/*.tex`. Related work cites only references marked
  `verified=yes` in `docs/research/related-work.csv`.
- **Acceptance:** `latexmk` builds, and `.venv/Scripts/python paper/check_numbers.py` confirms that every table file matches the archived results hash. NEEDS HUMAN: supervisor review.

## P7-02 — Documentation site
- **Owner:** sonnet · **Depends on:** P4-15 · **Read first:** `docs/03`, `docs/09`
- **Files:** `mkdocs.yml`, `docs-site/` (index, quickstart, concepts, cli, sdk, motor tutorial, faq), `pyproject.toml` (a `docs` extra: `mkdocs-material`, `mkdocstrings[python]`), `.github/workflows/ci.yml` (a docs job)
- **Spec:** pages:
  - Quickstart.
  - Concepts (claims, evidence, freshness, policies; from `docs/03`).
  - CLI reference (generated from Typer).
  - Python SDK reference (mkdocstrings).
  - The motor tutorial.
  - "Add ReVal to your project".
  - FAQ/limitations: T9 undeclared drift, and that ReVal is not a certification tool.
- **Acceptance:** `mkdocs build --strict` passes locally and in CI.

## P7-03 — Tutorial: add ReVal to a new project
- **Owner:** sonnet+human-review · **Depends on:** P7-02, P4-16 · **Read first:** `docs/00` S6
- **Files:** `examples/beam_toy/` (a tiny second domain with an analytic truth model: a cantilever beam deflection claim), `docs-site/tutorial-new-project.md`, `tests/integration/test_tutorial_beam.py`
- **Spec:** start from an empty folder: `reval init`, declare 2 requirements, 1 analytic producer, and 1 surrogate-model producer; change a parameter; run `diff`, `plan`, `run`, and `report`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_tutorial_beam.py` runs the tutorial's commands end to end. NEEDS HUMAN: a dry run by one person who didn't write the code, timed against the < 1 hour target (S6).

## P7-04 — Packaging + install test
- **Owner:** sonnet · **Depends on:** P7-02 · **Read first:** `pyproject.toml`
- **Files:** `pyproject.toml` (add `build` to the `dev` extra; include the templates as package data), `.github/workflows/ci.yml` (a `package` job)
- **Spec:** `python -m build` produces a wheel and an sdist. The CI job installs the wheel in a fresh venv on Ubuntu and Windows, then runs `reval --help` and the tutorial integration test.
  The version is bumped to `1.0.0` only in P7-07.
- **Acceptance:** `.venv/Scripts/python -m build` succeeds locally, and the `package` CI job is green.

## P7-05 — End-to-end reproduction script
- **Owner:** sonnet · **Depends on:** P5-16 · **Read first:** `docs/00` S1
- **Files:** `scripts/reproduce_all.sh`, `scripts/reproduce_all.ps1`, `REPRODUCE.md`
- **Spec:** from a clean clone plus the dataset, run in order:
  1. install;
  2. prepare the data;
  3. train;
  4. calibrate;
  5. LPTN;
  6. sensitivities;
  7. bench smoke (or full with `--full`);
  8. figures.
  The script prints the result hashes and compares them with the archived ones.
- **Acceptance:** NEEDS HUMAN: measure S1 (< 30 min without the full bench) and record it in `REPRODUCE.md`. Runnable check: `bash -n scripts/reproduce_all.sh` succeeds, and the PowerShell parser accepts the `.ps1`.

## P7-06 — Poster, demo video, defense slides
- **Owner:** human · **Depends on:** P7-01 · **Read first:** `docs/00`
- **Spec:** a 5-minute demo video of the coolant-change story (diff → stale claims → plan → run → report), a defense deck, and a poster that reuses the paper figures.
- **Acceptance:** NEEDS HUMAN: supervisor sign-off.

## P7-07 — Release v1.0.0
- **Owner:** sonnet+human-review · **Depends on:** P7-04, P7-05 · **Read first:** `README.md` (license)
- **Files:** `CHANGELOG.md` (Keep a Changelog), `CITATION.cff`, `LICENSE` (the student chooses it per the institution's IP policy), `pyproject.toml` (version)
- **Spec:** bump the version, tag `v1.0.0`, and create a GitHub release with the wheel, the results archive hash, and the citation.
- **Acceptance:** `git tag --list v1.0.0` prints the tag, and `pip install` from the release wheel works in a fresh venv. NEEDS HUMAN: the license choice and the push of the tag.

## P7-08 — arXiv preprint / submission
- **Owner:** human · **Depends on:** P7-01 · **Read first:** the venue's rules
- **Spec:** with supervisor approval only. Check the venue's dual-submission rules first.
