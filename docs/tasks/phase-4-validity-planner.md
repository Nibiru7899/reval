# Phase 4 — Validity engine + planner (roadmap weeks 15–18, milestone M4)

**Read first for every task:** `AGENTS.md`, `docs/03-domain-model.md`, `docs/04-algorithms.md` (A4–A7), `docs/10-interfaces.md`.
**Phase goal (M4 DoD):** `reval diff → plan → run → report` works end to end on the motor example. The planner matches brute force on small random instances.

---

## P4-01 — Split-conformal utilities (`reval.uq.conformal`)
- **Owner:** sonnet · **Depends on:** P2 done
- **Files:** `src/reval/uq/__init__.py`, `src/reval/uq/conformal.py`, `tests/unit/uq/test_conformal.py`
- **Spec:**
  1. `conformal_quantile(scores: np.ndarray, alpha: float) -> float`: returns `sorted(scores)[ceil((n+1)(1-alpha)) - 1]`, or `math.inf` if that index is ≥ n. Raise `ValueError` for alpha outside (0, 1) or empty scores.
  2. `class SplitConformal`: `fit(residuals_abs, alpha) -> Self` stores `q_hat`. `interval(point: float) -> tuple[float, float]`.
  3. `class GroupedSplitConformal`: one `q_hat` per group key (duty-cycle length class). `interval(point, group)` raises `KeyError` for unknown groups (fail-closed).
  4. Pure numpy. No I/O.
- **Acceptance:** `pytest tests/unit/uq -q` passes. Include tests for: (a) the exact quantile index on n=9, alpha=0.1; (b) inf when n is too small; (c) Hypothesis: the empirical coverage on i.i.d. normal residuals, n=2000, is ≥ 1-alpha-0.02 over 20 seeds.
- **Out of scope:** CQR (that's ablation A5, P5-13).
- **Pitfalls:** off-by-one in the quantile index. Don't use `np.quantile` interpolation.

## P4-02 — Applicability domain (`reval.uq.domain`)
- **Owner:** sonnet · **Depends on:** P4-01
- **Files:** `src/reval/uq/domain.py`, `tests/unit/uq/test_domain.py`
- **Spec:**
  1. `@dataclass(frozen=True) DomainReport`: `inside: bool`, `first_violation: int | None`, `violating_features: tuple[str, ...]`, `max_distance: float`, `threshold: float`, `frac_outside: float`, and `to_dict()` (JSON-safe, rounded to 6 decimals).
  2. `class ApplicabilityDomain(feature_names, k=10, box_quantiles=(0.005, 0.995), dist_quantile=0.99)`. `fit(X_train, X_calib)` standardizes on train, builds a `scipy.spatial.cKDTree`, sets the box from train quantiles and the threshold τ from the calibration kNN mean distance quantile. `check(X, mode="strict" | "relaxed", relaxed_frac=0.01) -> DomainReport`.
  3. Strict: inside iff every row passes the box and the distance check. Relaxed: inside iff frac_outside ≤ relaxed_frac.
  4. `to_state()` / `from_state()` for joblib-free serialization (numpy arrays + params).
- **Acceptance:** tests. A training cloud plus a far point gives `inside=False` with the right feature named. The first_violation index is correct. Determinism: two fits on the same data give identical reports.
- **Pitfalls:** standardize with train stats only. A zero-variance feature must not divide by zero (use std=1).

## P4-03 — Motor ML producers emit conformal + AD evidence
- **Owner:** sonnet · **Depends on:** P4-02, P1 (models, cycles), P2 (SDK)
- **Files:** `examples/motor_thermal/motor/producers.py`, `examples/motor_thermal/scripts/calibrate.py`, `examples/motor_thermal/tests/test_producers_ml.py`
- **Spec:**
  1. `calibrate.py` computes non-overlapping-window peak residuals on `calib` profiles per length class (A5), fits `GroupedSplitConformal` and `ApplicabilityDomain`, and saves them to `models/uq_<model>.joblib`. This is an artifact `derived_from` the model + measures + splits.
  2. `predict_peak_m1` (and m2/m3) produce `EvidenceResult` with `interval` = conformal interval on the peak, `in_domain` = AD strict check on the trajectory features (drive-map AD AND model AD), and `domain_report` = merged dicts.
  3. Declare `depends_on` the model, the uq artifact, the drive map, the cooling params selectors actually read. `Scope.box` = bounding box of the cycle trajectory over (torque, motor_speed, coolant, ambient).
- **Acceptance:** with the data marker `pytest -m data examples/motor_thermal/tests/test_producers_ml.py` passes. A recorded test cycle is in domain. A synthetic cycle with coolant 95 °C is out of domain with `coolant` listed. Without data, the tests are skipped (not failed).
- **Pitfalls:** `Context.load` must be used for every artifact (undeclared reads raise). Temperatures are absolute °C, interval half-widths are K.

## P4-04 — Verdicts & status: AD/conformal integration tests
- **Owner:** sonnet · **Depends on:** P4-03, P2 status engine
- **Files:** `tests/unit/core/test_verdicts_ml.py`, `tests/property/test_ml_gate.py`
- **Spec:** No new engine code expected. If anything is missing, fix it in `reval/core/verdicts.py` per `docs/03` §2. Tests: an ML evidence out of domain is always `INCONCLUSIVE` with `OUT_OF_DOMAIN`, regardless of interval (property test over random intervals). GE/LE symmetry. Boundary inclusivity (`hi == L` → PASS, `lo == L` → not FAIL).
- **Acceptance:** `pytest tests/unit/core tests/property -q` passes.

## P4-05 — Obligations & candidate generation (`reval.core.planner`)
- **Owner:** sonnet · **Depends on:** P4-04
- **Files:** `src/reval/core/planner.py` (part 1), `tests/unit/core/test_planner_candidates.py`
- **Spec (signatures in `docs/10-interfaces.md`):**
  1. `build_problem(snapshot, assessments, fresh_evidence, availability, known_out_of_domain) -> PlanningProblem`.
  2. Claims to plan: status ∈ {STALE, INCONCLUSIVE}. For each clause and conjunct not pre-satisfied by fresh PASS evidence → an `Obligation`.
  3. Candidates: one per (producer, subject) that is available (`availability[(producer_id, subject_id)]`) and matches kind, quantity, and fidelity. Exclude ML candidates for `in_domain` conjuncts when `(producer_id, subject_id) ∈ known_out_of_domain`.
  4. Each candidate lists every obligation it can satisfy (across claims sharing the subject).
  5. Deterministic ordering: sort obligations by (claim_id, clause, conjunct) and candidates by id.
- **Acceptance:** hand-built fixtures: a bench run on DC-07 satisfies both the pm and sw obligations. A pre-satisfied conjunct produces no obligation. An unavailable bench produces no candidate.
- **Pitfalls:** a claim with a clause that has zero candidates for some conjunct: that clause can't be chosen, but other clauses still can.

## P4-06 — CP-SAT min-cost planner
- **Owner:** sonnet · **Depends on:** P4-05
- **Files:** `src/reval/core/planner.py` (part 2), `tests/unit/core/test_planner_ilp.py`
- **Spec:**
  1. `plan(problem, planner="ilp", objective="min_cost", budget=None) -> RevalidationPlan`.
  2. Formulation exactly as `docs/04` A7. Integer costs = `round(cost*100)`. M = sum(all integer costs) + 1. Weights low 1, medium 3, high 10.
  3. Independence: a single candidate can't be used for two conjuncts of the same clause. Model this with assignment vars `x[c,k,r,j] ≤ z_j`, `Σ_j x[c,k,r,j] ≥ y[c,k]`, `Σ_r x[c,k,r,j] ≤ 1`.
  4. Solver params: `num_workers=1`, `random_seed=0`, `max_time_in_seconds=10`. Record `solver_status` (OPTIMAL/FEASIBLE/…).
  5. `unrestorable` = claims with u_c = 1. `chosen_clauses` from y.
- **Acceptance:** `tests/unit/core/test_planner_ilp.py` checks against **brute force over all candidate subsets** on 200 random instances (≤ 10 candidates, ≤ 4 claims, seeded) and the costs must match exactly. Determinism: same input → identical plan JSON.
- **Pitfalls:** `ortools` import lives only in this module. Don't leak solver objects into returned models.

## P4-07 — Budgeted variant (max-restored)
- **Owner:** sonnet · **Depends on:** P4-06
- **Files:** `src/reval/core/planner.py`, `tests/unit/core/test_planner_budget.py`
- **Spec:** `objective="max_restored"` requires `budget`. Maximize `Σ w_c (1-u_c)` s.t. `Σ cost z ≤ budget`. Tie-break: secondary objective minimize cost (lexicographic: weight × (M) − cost).
- **Acceptance:** brute-force comparison as in P4-06. Monotonicity property: a larger budget never restores less weight.

## P4-08 — Greedy and "all" planners
- **Owner:** sonnet · **Depends on:** P4-06
- **Files:** `src/reval/core/planner.py`, `tests/unit/core/test_planner_greedy.py`
- **Spec:** greedy = repeatedly pick the candidate with max (newly-satisfied weighted obligations / cost), stop when every claim has a fully covered clause or there's no progress, then prune redundant runs in reverse order. "all" = select every candidate. Both return `RevalidationPlan` with `planner` set.
- **Acceptance:** greedy cost ≥ ILP cost on all random instances. Greedy covers everything ILP covers. "all" cost = Σ all candidates.

## P4-09 — `reval plan` CLI
- **Owner:** sonnet · **Depends on:** P4-08, P3 CLI
- **Files:** `src/reval/services/project.py` (`Project.plan`), `src/reval/cli/main.py`, `tests/integration/test_cli_plan.py`
- **Spec:** `reval plan [--budget N] [--planner ilp|greedy|all] [--format table|json]`. It stores the plan in the store and prints runs, costs, discharged obligations, and unrestorable claims. Availability and OOD sets come from producer `available_for` and the latest ML evidence per (producer, subject, model version).
- **Acceptance:** integration test on the toy example project (`tests/fixtures/toy_project/`) prints a deterministic table. `--format json` validates against the `RevalidationPlan` schema.

## P4-10 — Job runner + `reval run`
- **Owner:** sonnet · **Depends on:** P4-09
- **Files:** `src/reval/services/jobs.py`, `src/reval/services/project.py` (`Project.run_plan`), CLI, `tests/integration/test_cli_run.py`
- **Spec:** an in-process runner executes planned runs in plan order, writes `jobs` rows (queued → running → done/failed), and appends evidence. A failure in one run marks that job failed and continues. `reval run [--plan ID] [--only PRODUCER]`.
- **Acceptance:** on the toy project, `diff → plan → run` turns a STALE claim into SUPPORTED. A producer raising an exception yields a failed job and no evidence, and the claim stays STALE.
- **Pitfalls:** evidence is append-only. Never update an existing evidence row.

## P4-11 — Re-assessment loop + invariant I6
- **Owner:** sonnet · **Depends on:** P4-10
- **Files:** `src/reval/services/project.py`, `tests/property/test_plan_soundness.py`
- **Spec:** after `run`, re-assess automatically and print before/after statuses. I6 property test: with a fake producer registry whose runs always return decisive PASS verdicts, every non-unrestorable planned claim ends in SUPPORTED (Hypothesis-generated toy problems).
- **Acceptance:** `pytest tests/property/test_plan_soundness.py` passes with 200 examples.

## P4-12 — Canonical report JSON
- **Owner:** sonnet · **Depends on:** P4-11
- **Files:** `src/reval/report/model.py`, `src/reval/report/build.py`, `tests/golden/test_report_json.py`
- **Spec:** a `Report` pydantic model with exactly the fields in `docs/09` "Report format". `report_hash` = SHA-256 of the canonical JSON without `report_hash`. **The disclaimer string is a constant and is mandatory.**
- **Acceptance:** golden-file test on the toy project. The hash is stable across two runs.

## P4-13 — Markdown + HTML rendering, `reval report`
- **Owner:** sonnet · **Depends on:** P4-12
- **Files:** `src/reval/report/render.py`, `src/reval/report/templates/report.html.j2` (add `jinja2` to deps), CLI
- **Spec:** `reval report [--html] [--out PATH]`. HTML is self-contained (inline CSS, no external requests). Statuses are shown with icon + text (not color only). The disclaimer is at the top.
- **Acceptance:** golden Markdown test. An HTML smoke test checks the disclaimer and all claim ids are present.
- **Pitfalls:** never write "safe" or "certified" in templates (AGENTS rule 9). Add a test that greps the templates for those words.

## P4-14 — `reval explain CLAIM`
- **Owner:** sonnet · **Depends on:** P4-12
- **Files:** `src/reval/report/explain.py`, CLI, `tests/golden/test_explain.py`
- **Spec:** deterministic text tree: claim → status → reasons → satisfied/failed clauses → evidence (verdict, freshness, interval, producer) → dependencies (selector@hash[:8]).
- **Acceptance:** golden test.

## P4-15 — M4 demo script + review
- **Owner:** sonnet+human-review · **Depends on:** P4-13, P4-14
- **Files:** `examples/motor_thermal/demo_full.sh`, `examples/motor_thermal/demo_full.ps1`
- **Spec:** scripted: baseline snapshot → commit a coolant change → `reval diff HEAD~1 HEAD` → `plan` → `run` → `report --html`.
- **Acceptance:** runs from a clean clone with data present. The human checks the report wording and numbers. Update `docs/07-roadmap.md` M4 status.
