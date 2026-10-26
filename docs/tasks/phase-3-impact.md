# Phase 3 — Change impact (roadmap weeks 11–14)

**Binding spec:** `docs/10-interfaces.md` §4.2 (diff), §4.3 (freshness), §9 (gitio), §10 (services), and `docs/03` §4 / `docs/04` A2–A3.
**Safety rule for the whole phase:** every code path that marks evidence as not invalidated needs a test proving it fires *only* under its stated condition (ADR 0002, AGENTS rule 3).
Conventions: see the header of `phase-0-foundations.md`. Tests use the mini project fixture (`phase-2-core.md` header).

---

## P3-01 — Snapshot diff → `ChangeSet`
- **Owner:** sonnet · **Depends on:** P2-03, P2-16 · **Read first:** `docs/04` A2, `docs/10` §2 (`changes.py`), §4.2
- **Files:** `src/reval/core/diff.py`, `tests/unit/core/test_diff.py`
- **Spec:** `diff_snapshots(old: Snapshot, new: Snapshot) -> ChangeSet`, exactly the seven rules of `docs/10` §4.2:
  - artifact added/removed (including to/from `"missing"`);
  - yaml-fields `FIELD_ADDED/REMOVED/CHANGED` (with `old`, `new`, and `delta` when both are numeric and not bool);
  - dataframe `ROWS_ADDED/REMOVED/MODIFIED`, one change per kind per artifact, with sorted `groups`, the union of `columns`, and `rows_bbox` = the hull per `Change.rows_bbox` (MODIFIED hulls old **and** new);
  - a column-set change → `ARTIFACT_CHANGED`; model/file → `ARTIFACT_CHANGED`;
  - manifest entities → `REQUIREMENT_/ASSUMPTION_/POLICY_/SUBJECT_/CLAIM_CHANGED`, with add/remove as `detail="added"`/`"removed"` (no `*_ADDED` kinds) and old/new/delta for a limit change;
  - producer `code_hash`/`depends_on` → `PRODUCER_CODE_CHANGED`;
  - anything else → `UNKNOWN`.
  Output is sorted by (kind, target).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_diff.py`: one test per change kind (built from mini-project snapshots via `build_snapshot`); `diff(S, S)` is empty;
  the output is deterministic; a ROWS_MODIFIED change carries the right columns and an old+new hull bbox; adding a claim gives `CLAIM_CHANGED` with `detail="added"`.

## P3-02 — Git lock reader + `reval diff` (change set only)
- **Owner:** sonnet · **Depends on:** P3-01, P2-17 · **Read first:** ADR 0005, `docs/09` CLI, `docs/10` §9
- **Files:** `src/reval/gitio/git.py`, `src/reval/cli/main.py` (`diff` command), `tests/integration/test_cli_diff.py`
- **Spec:** `read_file_at_rev`, `snapshot_at_rev`, and `resolve_rev`, exactly as `docs/10` §9 (`subprocess.run([...])` with an argument list, never `shell=True`; nonzero exit → `GitError`
  with stderr). `reval diff A [B] [--format table|json]`: B defaults to the live working tree. It prints the change set **only**. The claim section and the status-based exit codes come in P3-06.
  Here the exit code is 0 on success and 3 on a `RevalError` (for example `LockNotFoundError`).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_cli_diff.py`:
  - Setup: create a temp git repo from a copy of the mini project with fixed `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env, run `reval snapshot --write`, commit, edit `/load/scale`, run `reval snapshot --write` again, and commit.
  - `reval diff HEAD~1 HEAD --format json` contains exactly one `FIELD_CHANGED` with target `params#/load/scale`.
  - Exit code is 0.
  - A revision without a lock exits 3.
- **Pitfalls:** pass git paths with forward slashes. Never interpolate user strings into a shell.

## P3-03 — Freshness: hard failures, exact, relevance, invalidation (fail-closed skeleton)
- **Owner:** sonnet · **Depends on:** P3-01, P2-15 · **Read first:** `docs/03` §4, `docs/04` A3, ADR 0002, `docs/10` §4.3
- **Files:** `src/reval/core/freshness.py`, `tests/unit/core/test_freshness.py`
- **Spec:** `FreshnessResult`, `classify_evidence`, and `classify_all`, exactly as `docs/10` §4.3 steps 0–2 and 4. For now, **no excuses**: every relevant change invalidates.
  Implement relevance rules (a)–(f) completely, including SUBJECT_CHANGED (D2), derived-closure changes (D3), and the UNKNOWN rule in the exact shortcut (D13).
  A missing old snapshot → INVALIDATED with `UNKNOWN_CHANGE`. Waiver hard failures per step 0.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_freshness.py`:
  - An unrelated field change → FRESH_EXACT; a related field → INVALIDATED (`MISSING_TOLERANCE`).
  - A whole-artifact dep plus any change → INVALIDATED; a producer code change → INVALIDATED.
  - UNKNOWN on a dep artifact → INVALIDATED, while UNKNOWN on an unrelated artifact → FRESH_EXACT.
  - SUBJECT_CHANGED on the evidence's subject → INVALIDATED.
  - An upstream `data` change → `surrogate`-based evidence INVALIDATED.
  - A waiver whose requirement changed → INVALIDATED.

## P3-04 — Freshness: out-of-scope rows
- **Owner:** sonnet · **Depends on:** P3-03 · **Read first:** `docs/03` §4, `docs/10` §4.3 step 3 (rows)
- **Files:** `src/reval/core/freshness.py`, `tests/unit/core/test_freshness_rows.py`
- **Spec:** the ROWS_* excuse exactly as step 3: only through rule (a) matching a **column-selector** dependency on a dataset (never a whole-artifact dep, never via rule (f)),
  `rows_bbox` not None, and ≥ 1 variable shared by `rows_bbox` and `scope.box` with disjoint intervals (D12). An empty scope box never qualifies.
  All excused with zero inflation → FRESH_OUT_OF_SCOPE.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_freshness_rows.py`:
  - Disjoint `x` ranges → FRESH_OUT_OF_SCOPE; overlapping → INVALIDATED.
  - An empty box → INVALIDATED; a whole-artifact `data` dep → INVALIDATED.
  - Evidence depending on the derived `surrogate` → INVALIDATED even when the rows are out of scope.
  - A ROWS_MODIFIED change whose old bbox overlaps but new bbox doesn't → INVALIDATED.

## P3-05 — Tolerance carry-forward + I5
- **Owner:** sonnet · **Depends on:** P3-03 · **Read first:** `docs/03` §4, `docs/04` A3, `docs/10` §4.3 step 3 (fields), `carry_forward`
- **Files:** `src/reval/core/freshness.py`, `tests/unit/core/test_freshness_tolerance.py`, `tests/property/test_invariants_freshness.py`
- **Spec:** the FIELD_CHANGED excuse: a tolerance with `tol.selector == c.target`, and old **and** new values inside `valid_range`. It contributes `safety_factor · sensitivity · |delta|`
  (κ applied once, D14). `tol.output_unit != difference_unit(e.result.unit)` → `ValueError`. All excused with inflation > 0 → CARRY_FORWARD. CARRY_FORWARD with no interval →
  INVALIDATED (`MISSING_TOLERANCE`). `carry_forward(e, fr, new) -> Evidence`, exactly as §4.3 (e′ re-hashed, `derived_from_evidence=e.id`, id recomputed). The status engine
  (P2-09) already accepts CARRY_FORWARD items with `original`. Don't change `status.py`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_freshness_tolerance.py tests/property/test_invariants_freshness.py`:
  - A small Δ within range → CARRY_FORWARD with exactly the expected inflation.
  - A new value outside `valid_range` → INVALIDATED.
  - A whole-artifact dep plus a tolerance on a changed leaf → INVALIDATED. Tolerances only excuse changes matched through a pointer-selector dep.
  - A wrong `output_unit` raises.
  - The carried interval can flip PASS → INCONCLUSIVE, and assessing it then gives STALE.
  - **I5** (monotone inflation) is a Hypothesis property.

## P3-06 — Wire freshness into `Project.assess` + `reval diff` claim section
- **Owner:** sonnet · **Depends on:** P3-02, P3-04, P3-05 · **Read first:** `docs/10` §10 (`assess` steps, `DiffReport`), `docs/09` exit codes
- **Files:** `src/reval/services/project.py`, `src/reval/cli/main.py`, `src/reval/cli/render.py`, `tests/integration/test_assess_freshness.py`, `tests/integration/test_cli_diff_claims.py`
- **Spec:** replace the Phase 2 placeholder with the eight `assess` steps of `docs/10` §10: carried items become `AssessInput(carry_forward(...), CARRY_FORWARD, original=e)` and are **never stored**;
  assessments are a new batch. Add `Project.diff(a, b) -> DiffReport` (`changes`, `freshness`, `before`, `after`, `affected_claims`). `reval diff` gains the claim section (old → new status
  with reasons) and the `docs/09` exit codes based on the `after` statuses.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_assess_freshness.py tests/integration/test_cli_diff_claims.py`:
  - Setup: in the temp git repo from P3-02, run `reval run --all` before the edit (evidence lives in the git-ignored `.reval/` store).
  - A small `/load/scale` change → `sim_temp` evidence CARRY_FORWARD, `predict_temp` INVALIDATED, and `C-SHAFT` unaffected.
  - `reval diff HEAD~1 HEAD` lists the affected claims and exits 1.
  - Existing tests still pass.

## P3-10 — Property tests I3 and I7
- **Owner:** sonnet · **Depends on:** P3-06, P2-12 · **Read first:** `docs/03` §5
- **Files:** `tests/property/test_invariants_freshness.py`, `tests/property/strategies.py`
- **Spec:**
  - **I3:** for random projects plus random change sets, stripping all tolerances and scope boxes never yields more accepted claims. This includes the case where a FAIL item gets invalidated.
  - **I7:** `assess(S)` after `diff(S, S)` equals `assess(S)`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/property` passes under the `ci` profile.

## P3-07 — LPTN sensitivity estimation → tolerances
- **Owner:** sonnet+human-review · **Depends on:** P3-05, P1-08, P2-13 · **Read first:** `docs/04` A3 "Where tolerances come from", `docs/10` §12 (`sensitivities.py`)
- **Files:** `examples/motor_thermal/motor/sensitivities.py`, `examples/motor_thermal/scripts/sensitivities.py`, `examples/motor_thermal/params/tolerances.yaml`, `examples/motor_thermal/motor/producers.py`,
  `examples/motor_thermal/reval.yaml` (one sensitivity assumption per tolerance), `tests/unit/motor/test_sensitivities.py`
- **Spec:** `estimate_tolerances(params, field, grid, cycles, *, assumption_id, kappa=1.5) -> list[Tolerance]`, exactly as §12:
  - `sensitivity` = **raw** max |Δpeak/Δfield| by central differences over grid × cycles (≥ 5 grid points spanning `valid_range`), with `safety_factor=kappa`.
  - `input_unit` / `output_unit` declared (`output_unit="K"`), and `source = "fd on lptn@<hash>, grid=<n>"`.
  - Fields: `cooling#/flow_scale`, plus the LPTN `R` and `C` leaves.
  - `lptn_sim` attaches the tolerances from `tolerances.yaml`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_sensitivities.py`: a linear toy simulator recovers its slope, and the script output is byte-identical on rerun. NEEDS HUMAN: the magnitudes (K per unit) are plausible.

## P3-08 — Interim demo script
- **Owner:** sonnet · **Depends on:** P3-06, P3-07 · **Read first:** `docs/07` M3, `docs/02` §5
- **Files:** `examples/motor_thermal/demo_change.ps1`, `examples/motor_thermal/demo_change.sh`, `examples/motor_thermal/DEMO.md`
- **Spec:** on a throwaway branch:
  1. `reval snapshot --write`, `reval run --all`, commit.
  2. Edit `params/cooling.yaml` `flow_scale` 1.00 → 0.97, `snapshot --write`, commit, `reval diff HEAD~1 HEAD`. Expected: carry-forward on `lptn_sim`, stale thermal claims where the margin is too small, shaft claim untouched.
  3. A large change (0.75), then diff again. Expected: invalidation.
  4. Restore the original branch.
  The script appends its own output to `DEMO.md` between markers.
- **Acceptance:** NEEDS HUMAN: it runs end to end on a machine with data. Runnable check: `tests/integration/test_demo_script.py` (marked `data` and `slow`) runs the `.sh`/`.ps1` and asserts exit 0 and that the markers were filled.

## P3-09 — `reval diff --format markdown`
- **Owner:** sonnet · **Depends on:** P3-06 · **Read first:** `docs/09` (`diff`), P6-13 (consumer)
- **Files:** `src/reval/cli/render.py`, `src/reval/cli/main.py`, `tests/golden/test_diff_markdown.py`, `tests/golden/diff_markdown.md`
- **Spec:** a GitHub-flavoured Markdown rendering of `DiffReport`: a summary line ("N claims need revalidation"), a change table, and a claim table with status icon **and** text. The disclaimer goes at the bottom.
  It is deterministic (no timestamps).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/golden/test_diff_markdown.py` matches the golden file on the mini project's `/load/scale` scenario.
