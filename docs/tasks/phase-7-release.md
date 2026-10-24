# Phase 7 — Write-up and release (roadmap weeks 27–30)

**Read first:** `AGENTS.md` (rule 9: honest language; rule 10: numbers from scripts), `docs/research/paper-outline.md`, `docs/06-evaluation.md` §7.

---

## P7-01 — Paper draft
- **Owner:** human (sonnet assists with LaTeX scaffolding and figure inclusion only) · **Depends on:** P5-16
- **Files:** `paper/` (LaTeX, e.g. an IEEE or ACM template per the target venue), `paper/figures/` (copied by script from `bench/results/<hash>/figures`)
- **Spec:** follow `paper-outline.md`. Every number is pulled from `bench/results/<hash>/tables/*.tex` (generated) via `\input`. The related work uses only references verified in `docs/research/related-work.csv` (`verified=yes`).
- **Acceptance:** `latexmk` builds. A script `paper/check_numbers.py` checks that every number in `tables/*.tex` matches the archived results hash. The supervisor reviews it.

## P7-02 — Documentation site
- **Owner:** sonnet · **Depends on:** P4-15
- **Files:** `mkdocs.yml`, `docs-site/` (or reuse `docs/` with nav), API reference via `mkdocstrings`
- **Spec:** pages: Quickstart, Concepts (claims/evidence/freshness/policies, from `docs/03`), CLI reference (generated from Typer), Python SDK reference, the motor tutorial, "Add ReVal to your project", FAQ/limitations (T9 undeclared drift, not a certification tool).
- **Acceptance:** `mkdocs build --strict` passes in CI.

## P7-03 — Tutorial: add ReVal to a new project
- **Owner:** sonnet+human-review · **Depends on:** P7-02
- **Files:** `examples/beam_toy/` (a tiny second domain with an analytic truth model: a cantilever beam deflection claim), `docs-site/tutorial-new-project.md`
- **Spec:** start from an empty folder. `reval init`, declare 2 requirements, 1 analytic producer + 1 surrogate-model producer, change a parameter, and run `diff/plan/run/report`. It must take < 1 hour for a newcomer (S6).
- **Acceptance:** an integration test runs the tutorial commands end to end. A human dry-run with one person who didn't write the code.

## P7-04 — Packaging + install test
- **Owner:** sonnet · **Depends on:** P7-02
- **Spec:** `python -m build` produces a wheel + sdist. A CI job installs the wheel in a fresh venv on Ubuntu + Windows and runs `reval --help` and the tutorial integration test. Version is bumped to `1.0.0` only at P7-07.
- **Acceptance:** green CI job `package`.

## P7-05 — End-to-end reproduction script
- **Owner:** sonnet · **Depends on:** P5-16
- **Files:** `scripts/reproduce_all.sh`, `scripts/reproduce_all.ps1`, `REPRODUCE.md`
- **Spec:** from a clean clone + dataset: install → prepare data → train → calibrate → LPTN → sensitivities → bench smoke (or full with `--full`) → figures. It prints the result hashes and compares them with the archived ones.
- **Acceptance:** S1 (< 30 min without the full bench) is measured and recorded in `REPRODUCE.md`.

## P7-06 — Poster, demo video, defense slides
- **Owner:** human · **Depends on:** P7-01
- **Spec:** a 5-minute demo video of the coolant-change story (diff → stale claims → plan → run → report). Use the Slides artifact or PowerPoint for the defense deck. The poster reuses the paper figures.
- **Acceptance:** the supervisor signs off.

## P7-07 — Release v1.0.0
- **Owner:** sonnet+human-review · **Depends on:** P7-04, P7-05
- **Spec:** update `CHANGELOG.md` (Keep a Changelog), bump the version, tag `v1.0.0`, and create a GitHub release with the wheel + results archive hash + citation (`CITATION.cff`). Choose and add the LICENSE (human decision, per the institution's IP policy).
- **Acceptance:** the tag exists. `pip install` from the release wheel works.

## P7-08 — arXiv preprint / submission
- **Owner:** human · **Depends on:** P7-01
- **Spec:** with supervisor approval only. Check the venue's dual-submission rules first.
