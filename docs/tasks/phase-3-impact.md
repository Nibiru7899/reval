# Phase 3 — Change impact (roadmap weeks 11–14)

**Binding spec:** `docs/10-interfaces.md` (core.diff, core.freshness, gitio) and `docs/03` §4 / `docs/04` A2–A3.
**Safety rule for the whole phase:** every new code path that marks evidence as not invalidated needs a test proving it fires *only* under its stated condition (ADR 0002).
Conventions: see the header of `phase-0-foundations.md`.

---

## P3-01 — Snapshot diff → `ChangeSet`
- **Owner:** sonnet · **Depends on:** P2-03, P2-04 · **Read first:** `docs/04` A2
- **Files:** `src/reval/core/diff.py`, `tests/unit/core/test_diff.py`
- **Spec:** `diff_snapshots(old, new) -> ChangeSet`. Compare per artifact: added/removed artifacts; field hashes (FIELD_ADDED / FIELD_REMOVED / FIELD_CHANGED with `old`, `new`, `delta` when both numeric);
  dataframe groups (ROWS_ADDED for new groups, ROWS_REMOVED, ROWS_MODIFIED with `groups`, `columns`, and `rows_bbox` = union of old and new bboxes of affected groups);
  `model` content-hash change → ARTIFACT_CHANGED (reason detail: upstream vs. file); `file` change → ARTIFACT_CHANGED. Manifest entities: REQUIREMENT_CHANGED (with old/new limit),
  ASSUMPTION_CHANGED, POLICY_CHANGED, CLAIM_ADDED/CLAIM_REMOVED, PRODUCER_CODE_CHANGED. Anything unclassifiable → UNKNOWN. Output sorted by (kind, target).
- **Acceptance:** one test per change kind; `diff(S,S)` is empty; determinism; a row change carries the correct columns and bbox.

## P3-02 — Git lock reader + `reval diff`
- **Owner:** sonnet · **Depends on:** P3-01, P2-11 · **Read first:** ADR 0005, `docs/09` CLI
- **Files:** `src/reval/gitio/{__init__,git,lockfile}.py`, CLI `diff` command, `tests/integration/test_cli_diff.py`
- **Spec:** `read_file_at_rev(repo_root, rev, relpath) -> bytes` via `subprocess.run(["git","show",f"{rev}:{relpath}"], check=True, capture_output=True)`. A missing file → `LockNotFoundError` with guidance.
  `snapshot_at_rev(repo_root, rev, project_subdir) -> Snapshot`. CLI `reval diff A [B]` (B defaults to the working tree): prints the change set, then for each claim old → new status with reasons.
  `--format json` emits a `DiffReport` (spec in `10-interfaces.md`).
- **Acceptance:** the integration test makes a temp git repo from `tests/fixtures/mini_project`, commits a lock, edits a param + rewrites the lock + commits, then `reval diff HEAD~1 HEAD` reports the FIELD_CHANGED and the affected claim; exit code 1.
- **Pitfalls:** on Windows, pass paths to git with forward slashes. Don't rely on the shell. Never run `git` with user-controlled strings via `shell=True`.

## P3-03 — Freshness: exact + invalidated (fail-closed skeleton)
- **Owner:** sonnet · **Depends on:** P3-01, P2-07 · **Read first:** `docs/03` §4, `docs/04` A3, ADR 0002
- **Files:** `src/reval/core/freshness.py`, `tests/unit/core/test_freshness.py`
- **Spec:** `FreshnessResult` and `classify_evidence(e, old, new, changes) -> FreshnessResult`. Step 1: if every dep's `version_hash == new.selector_hash(dep ref)`, the producer code hash is unchanged,
  and no in-scope assumption changed → FRESH_EXACT. Step 2: relevant changes = selector match (prefix rules on JSON pointers; `*` matches all; column lists intersect) + assumption + producer-code changes.
  Anything else → INVALIDATED with one `Reason` per relevant change (`EVIDENCE_INVALIDATED`, `UNKNOWN_CHANGE`, …). `classify_all(...)` is sorted by evidence id.
  Evidence whose `provenance.snapshot_id` isn't available → INVALIDATED (`UNKNOWN_CHANGE`).
- **Acceptance:** tests: an unrelated field change → FRESH_EXACT; a related field → INVALIDATED; `*` dep + any change → INVALIDATED; producer code change → INVALIDATED; UNKNOWN → INVALIDATED.

## P3-04 — Freshness: out-of-scope rows
- **Owner:** sonnet · **Depends on:** P3-03 · **Read first:** `docs/03` §4 bullet 2
- **Files:** `src/reval/core/freshness.py`, tests.
- **Spec:** if every relevant change is ROWS_ADDED/ROWS_MODIFIED/ROWS_REMOVED on a dataset the evidence depends on **directly**, and for each change there is ≥ 1 variable shared by `rows_bbox` and `e.scope.box`
  whose intervals are disjoint → FRESH_OUT_OF_SCOPE. An empty scope box never qualifies. A change to a model derived from those rows is a separate ARTIFACT_CHANGED and still invalidates.
- **Acceptance:** tests: disjoint coolant ranges → out of scope; overlap → invalidated; empty box → invalidated; dataset + derived model both changed → invalidated.

## P3-05 — Tolerance carry-forward
- **Owner:** sonnet · **Depends on:** P3-03 · **Read first:** `docs/03` §4 bullet 3, `docs/04` A3
- **Files:** `src/reval/core/freshness.py` (`carry_forward`), `src/reval/core/status.py` (use carried intervals), tests.
- **Spec:** FIELD_CHANGED with numeric delta, a matching `Tolerance` (exact selector), old and new values inside `valid_range`, and the tolerance's `assumption_id` (if any) unchanged → excused, contributing
  `κ·s·|Δ|` to the inflation. If every relevant change is excused (out-of-scope rows contribute 0) and the inflation is > 0 → CARRY_FORWARD.
  `carry_forward(e, result) -> Evidence` builds a new evidence item via `Evidence.create` with `interval.widen(inflation)`, `derived_from_evidence=e.id`, and the same deps updated to the new hashes.
  The status engine uses the carried item in place of the original.
- **Acceptance:** tests: small Δ within range → CARRY_FORWARD with the exact inflation; Δ leaving `valid_range` → INVALIDATED (`MISSING_TOLERANCE` detail "out of valid range"); the inflated interval can flip PASS → INCONCLUSIVE.
  Property test **I5** (monotone inflation) in `tests/property/test_invariants_freshness.py`.

## P3-06 — Wire freshness into `Project.assess` + I3 property test
- **Owner:** sonnet · **Depends on:** P3-03…P3-05 · **Read first:** `10-interfaces.md` (services)
- **Files:** `src/reval/services/project.py`, `tests/property/test_invariants_freshness.py`
- **Spec:** replace the Phase 2 placeholder: group stored evidence by `provenance.snapshot_id`, load each old snapshot from the store, diff once per old snapshot, classify, carry forward, then `assess_all`.
  The previous assessment = the latest stored assessments from a different snapshot.
  **I3:** stripping all tolerances and scopes from random projects never yields more accepted claims.
- **Acceptance:** all existing tests pass; I3 passes at `max_examples=200`.

## P3-07 — LPTN sensitivity estimation → tolerances
- **Owner:** sonnet+human-review · **Depends on:** P3-05, P1-08 · **Read first:** `docs/04` A3 "Where tolerances come from"
- **Files:** `examples/motor_thermal/scripts/sensitivities.py`, `examples/motor_thermal/params/tolerances.yaml`, `motor/producers.py` (attach tolerances to the outputs)
- **Spec:** for each tolerated parameter (cooling `flow_lpm` / R_coolant, `inlet_temp`, LPTN `R` and `C` fields) and each subject length class: central finite differences of the peak w.r.t. the
  parameter over a grid spanning `valid_range` (≥ 5 points), sensitivity = max |∂peak/∂p|, with `source` = "fd on lptn@<hash>, grid=<n>, κ=<κ>". Also write a sensitivity `Assumption` per tolerance.
- **Acceptance:** the script is deterministic (same YAML bytes on rerun); the unit test on a linear toy simulator recovers the slope; a human checks magnitudes are plausible (K per unit).

## P3-08 — Interim demo script
- **Owner:** sonnet · **Depends on:** P3-02, P3-06, P3-07, P2-13 · **Read first:** `docs/07` M3, `docs/02` §5
- **Files:** `examples/motor_thermal/demo_change.ps1`, `demo_change.sh`, `examples/motor_thermal/DEMO.md`
- **Spec:** a throwaway branch: commit the baseline lock → edit `params/cooling.yaml` (small change) → `reval snapshot --write` → commit → `reval diff HEAD~1 HEAD` (shows carry-forward + stale thermal claims, shaft claim untouched)
  → a large change → diff again (shows invalidation). Restores the original branch at the end. `DEMO.md` explains each output block.
- **Acceptance:** runs end to end on a machine with data. The output is captured in `DEMO.md` as a code block produced by the script (not hand-written).
