# Plan audit — binding decisions (2026-10-26)

Three read-only audits (core semantics, task backlog, research/domain) produced 79 findings. These are the rulings applied to the plan.
Where a doc disagrees with this record, this record wins until the doc is fixed.

## Core semantics (docs/03, 04, 10, ADR 0005, `domain/status.py`)

| # | Decision |
|---|---|
| D1 | `Snapshot.id = content_id(snapshot, exclude={"id", "git_rev"})`. This is the only definition (no "Merkle", no `(artifact_id, content_hash)` formula). `write_lock` writes `git_rev: null`. `read_lock` recomputes the id and raises `StoreError` on mismatch. |
| D2 | `SUBJECT_CHANGED` targeting `e.subject_id` is relevant to that evidence and never excused (`EVIDENCE_INVALIDATED`). |
| D3 | Every hasher folds upstream hashes when `derived_from` is non-empty: `content_hash = sha256(own + "|" + "|".join(upstream content_hash, sorted))`. Field hashes stay own-only. Freshness treats any change in the transitive `derived_from` closure of a dep's artifact as relevant and never excused. |
| D4 | **History-free status.** `previous` is removed from the status rules and from `input_hash` (it is kept only for display/diff). Rule order: (1) VIOLATED: fresh eligible FAIL. (2) WAIVED. (3) STALE (lost fail): some evidence for the claim that would have FAILed with its recorded interval is now INVALIDATED, or was carried forward from FAIL to non-FAIL. (4) SUPPORTED. (5) STALE: some clause would be satisfied if INVALIDATED evidence were treated as fresh with its recorded interval. (6) INCONCLUSIVE. The enum declaration order no longer encodes the evaluation order. |
| D5 | Carry-forward: `assess` receives the derived `e′` **instead of** `e`. `e′` is materialized per assessment and never stored. `EvidenceUse` gains `derived_from_evidence: str \| None`. `assess_claim` raises `ValueError` on a CARRY_FORWARD item without `derived_from_evidence`. Symmetric widening can't turn PASS into FAIL, so "may even fail" is deleted. |
| D6 | `Producer.predictors: tuple[str, ...]` (the model artifacts that produce the quantity). Independent ⇔ different producer kind **and** disjoint `predictors`. Same text in 03, 05, and 10. |
| D7 | Planner: existing fresh PASS evidence enters as cost-0 candidates (the 10 §4.6 "drop" rule goes). Pairwise independence constraints `x_{j,o} + x_{j′,o′} ≤ 1` for incompatible candidates. Exclude `(producer, subject)` pairs that already have **FRESH_EXACT** evidence at this snapshot (carried-forward and out-of-scope items stay rerunnable; round 2). Lost-fail items add mandatory rerun obligations (round 2). `known_out_of_domain` excludes ML candidates regardless of the conjunct's `in_domain` flag. `RevalidationPlan.deferred` (restorable, over budget) is separate from `unrestorable` (no cover at infinite budget). Integer weights {1, 3, 10} and integer costs ×100. Tests assert `OPTIMAL`; a time-limited `FEASIBLE` result is recorded in `solver_status` and marked non-reproducible. |
| D8 | Default policies gain an analytic clause: `low` += `[analytic]`, `medium`/`high` += `[analytic{min_fidelity: 3}]`. |
| D9 | `run_producer` sets `scope.assumption_ids = sorted(set(output) ∪ set(producer.assumes))`. |
| D10 | `Waiver` gains `claim_id` and `requirement_hash`. It counts only for that claim, is invalidated when the requirement's content id changes, its deps are the union of the claim's evidence deps at creation, and its use is `used_in_clause=True`. Benchmarks contain no waivers. |
| D11 | `ctx.load(art)` needs a whole-artifact dep. With column deps it returns only the declared columns plus keys. With only pointer deps, use `ctx.param`. |
| D12 | Row-change excuse needs a **column-selector** dep (never a whole-artifact dep). `rows_bbox` = component-wise hull. `ROWS_MODIFIED` uses the hull of the old and new bboxes. |
| D13 | The exact-fresh shortcut also requires no `UNKNOWN` change that targets an artifact in `deps*(e)` or has an unparseable target. |
| D14 | `Tolerance.sensitivity` = raw max \|∂peak/∂f\|. κ lives only in `safety_factor` and is applied once. Tolerances use "old **and** new inside `valid_range`", and each relevant change is excused individually. A tolerance only excuses a change matched through a **pointer-selector** dep, never a whole-artifact dep (round 2). |
| D15 | Units are generic: `inflation`, `Interval.widen(delta)`, `Tolerance.input_unit`, `Tolerance.output_unit` (the difference unit: K for °C quantities, otherwise the same unit). A mismatch raises `ValueError`. |
| D16 | Producer code hash = sha256 over sorted `(relpath, bytes)` of every `.py` file in the producer's top-level package under the project root, plus the qualname. |
| D17 | `Tolerance.assumption_id` is required. |
| D18 | Assessments are append-only with PK `(snapshot_id, claim_id, seq)`. Reads return the highest seq. The Store protocol gains `put_job`, `update_job_state` (the only in-place update), `get_job`, `put_report`, `get_report`. |
| D19 | `report_hash` excludes `created_at` and `report_id`. The clock is injected by services/CLI, and tests pass a fixed value. |
| D20 | `reval.uq` has one owner: P1-05 (conformal) and P1-06 (domain). P4-01/P4-02 become "extend" tasks. The binding API is the one in 10 §5. Conformal with `n < ⌈1/α⌉ − 1` yields `q̂ = inf` → the producer emits `interval=None`, verdict INCONCLUSIVE, `MARGIN_BELOW_UNCERTAINTY`. |
| D21 | 10 §12 (motor) is rewritten to match the phase-1 specs, with EWMA `adjust=False` (causal, recursive, real-time equivalent). The producer names are `predict_pm_peak_<model>` / `predict_sw_peak_<model>`, `lptn_sim`, `bench_measure`, `shaft_check`, `current_limit_check`. Coolant flow enters only via `params/cooling.yaml#/flow_scale`, with `R_ic ∝ flow_scale^-0.8`. |
| D22 | Module owners: `reval/errors.py` (all errors, incl. `LockNotFoundError`) → P2-01. `domain/selectors.py` (`Selector`, RFC-6901 segment-wise prefix; whole artifact = bare `art`, written `*` in prose) → P2-02. `core/selectors.py::selector_hash` → P2-03. `manifest/snapshot_builder.py` → its own task after P2-05 and P2-06. Enums live in the existing `domain/status.py`. |
| D23 | ChangeKind = the list in 10 §2 (add/remove of a claim is `CLAIM_CHANGED`). `Change` gains `detail: str \| None`. ReasonCode gains `POLICY_SATISFIED` and `WAIVER_APPLIED`. 03 gets full ReasonCode and ChangeKind tables. |
| D24 | One test fixture project, `tests/fixtures/mini_project` (there is no `toy_project`), extended with a shaft params field + claim, two subjects, ML, physics, measurement, and analytic producers, and `available_for`. Its producers module is created in P2-06. |
| D25 | All tests live under `tests/` (`tests/bench/`, `tests/unit/motor/`). pytest uses `--import-mode=importlib` with pythonpath `src`, `.`, and `examples/motor_thermal`. |
| D26 | Agent workflow (**decided by the user, 2026-10-26**): after the checks pass and the reviewer has no open blocker or major finding, the agent runs `git switch main && git merge --ff-only <branch>` locally. It never pushes, rebases, or forces. A dependency counts as satisfied when it is `review` or `done`. The skill picks owners `sonnet` and `sonnet+human-review`. Checks run as `.venv/Scripts/python -m …`. |
| D27 | The API is single-project: `p = "default"`, root from `REVAL_PROJECT_ROOT`. |

## Research and evaluation (docs/00, 01, 05–09, research/*)

| # | Decision |
|---|---|
| R1 | UAR is a ratio of sums (pooled within each resample). Also report UAR* = bad accepts / all claims, and decision coverage. ReVal is non-inferior only if UAR is non-inferior **and** decision coverage ≥ B0 − 2 pp. |
| R2 | H1: one-sided 97.5 % upper bound of UAR_evidence(ReVal) < δ (B0 ≡ 0), **and** UAR_truth(ReVal) − UAR_truth(B0) < δ. UAR_truth is primary. Cost: the upper CI bound of the paired mean log(C_ReVal/C_B1) < 0. H1 is an intersection-union test. H2/H3 use Holm correction at α = 0.05. δ is justified from the pilot and also reported as a relative margin. |
| R3 | Stratified cluster bootstrap: strata = change type, clusters = base snapshot (≥ 30 distinct), 10,000 resamples. |
| R4 | Oracle: union of evidence referenced by any clause in S or S′. Common random numbers keyed by (scenario, producer, subject). ε = 0.1·median q̂ per target, pre-registered. Report recall, precision, and F2. RQ1 assumes a correct assessment engine, which is covered by property tests. |
| R5 | Tier A truth exists only for recorded **test** cycles. Optimizer/synthetic UAR_truth is computed in Tier B only. `reserve` profiles are never claim subjects. Tier A truth comes from S′ data. |
| R6 | H3 is a 2×2 design {O1, O3} × {point, ReVal-gated}, with N ≥ 50 optimizer runs per cell. Primary contrast: gated vs point on O1. |
| R7 | Tier B ML models are retrained on world-model trajectories. The world model is calibrated on train + reserve only. |
| R8 | Test split = the published generalization profiles plus extra profiles to reach ~20 %. Literature-comparable metrics are reported on the published subset. |
| R9 | Phase 6 starts after the M5 DoD (earliest week 24). The default UI is the static HTML report unless M5 is met by week 23. Real buffers are weeks 18 and 24. Postgres moves to the cut list. |
| R10 | Pre-registration is committed at the end of week 21, after a pilot on development seeds. The final run is in week 22 on fresh seeds. R8 (runtime) is rescored to L3/I2. |
| R11 | Citations: the license is CC BY-SA 4.0, and torque is an *estimate*. Add the Kaggle-requested TPEL 2021 citation, the TEC 2021 benchmark details, Wallscheid & Böcker 31(1):354–365, the full V&V 40 title (medical devices), NAS 2024 (DOI 10.17226/26894), Sandia PCMM SAND2007-5948, and OpenModelica traceability (MDPI Electronics 10(8):983, 2021). The UK digital-twin definition (GOV.UK, Oct 2025) is cited only for what it says. Drop the 2025 Springer survey, the 2026 ScienceDirect paper, and the Aug 2026 arXiv agents paper. |
| R12 | Smaller fixes: A5 = fixed margin, A8 = CQR. The claim count is ≈ 170. Recall target S2 = Tier A plus Tier B excluding T9. Roadmap week 10 = I1, I2, I4 (I3, I7 in Phase 3; corrected in round 2). Report "cost per claim decided". |

## Not applied

- Permission additions to `.claude/settings.json` that an auditor suggested (`git branch`, `.venv/Scripts/reval`, extra denies). That is the user's call. The skill uses commands that are already allowed, where possible.
- `Bash(git merge --ff-only:*)` was added to the allow list at the user's request (2026-10-26).

## Round 2 (re-verification, 2026-10-26)

A second read-only pass found 20 more defects. Rulings:
- Planner reruns: only FRESH_EXACT evidence blocks a rerun (D7). Lost-fail claims need a mandatory rerun of the failing producer.
- Tolerances excuse only pointer-selector matches (D14). The motor `lptn_sim` depends on `lptn#/R`, `lptn#/C` and `lptn#/loss`, not the whole `lptn`.
- `ReValSettings` lives in `src/reval/domain/settings.py` (so core can import it), and the SDK exposes it as `Context.settings`.
- `current_limit_check` has fidelity 3, so the medium analytic clause can support it.
- D3 is kept. The benchmark's T1/T3 expected effects now say that every `measures`-derived artifact is invalidated.
- I4 gains a supersede exception: a fresh same-producer item counts as new evidence.
- H2 and H3 now have explicit test forms in docs/06 §1 and in the pre-registration.
- Roadmap: P2-01 moves to week 3. EDA and limits move to weeks 3–4 (M1). Report work moves to week 17, which makes week 18 a real buffer. Stats, ablation and RQ4 harnesses move to week 20. The cut-line reference is now 5.
- ADR 0005: `--strict` is removed, and `reval status` only warns.
