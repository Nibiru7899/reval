# Phase 4 — Validity engine + planner (roadmap weeks 15–18, milestone M4)

**Read first for every task:** `AGENTS.md`, `docs/03-domain-model.md`, `docs/04-algorithms.md` (A4–A7), `docs/10-interfaces.md`.
**Phase goal (M4 DoD):** `reval diff → plan → run → report` works end to end on the motor example, and the planner matches brute force on small random instances (status `OPTIMAL`).
`reval.uq` was built in Phase 1 (P1-05, P1-06). Phase 4 only **extends** it. Any new public signature must be added to `docs/10` §5 in the same change.
Conventions: see the header of `phase-0-foundations.md`. Tests use the mini project fixture.

---

## P4-01 — Extend `reval.uq.conformal`: `GroupedSplitConformal`
- **Owner:** sonnet · **Depends on:** P1-05 · **Read first:** `docs/04` A5, `docs/10` §5
- **Files:** `src/reval/uq/conformal.py`, `examples/motor_thermal/motor/conformal.py` (refactor `PeakConformal` to use it, same public API), `docs/10-interfaces.md` §5 (add the signature), `tests/unit/uq/test_grouped_conformal.py`
- **Spec:** `class GroupedSplitConformal`: `__init__(self, alpha: float)`, `fit(self, y_true, y_pred, groups: Sequence[str]) -> GroupedSplitConformal` (one `SplitConformal` per group),
  `interval(self, y_pred: float, group: str) -> tuple[float, float] | None` (unknown group → `KeyError`, fail-closed; q = inf → None), and `q_by_group -> dict[str, float]`.
  Pure numpy.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/uq tests/unit/motor/test_motor_conformal.py`: per-group quantiles match `conformal_quantile`; an unknown group raises; the `PeakConformal` tests are unchanged and pass.

## P4-02 — Extend `reval.uq.domain`: combine domain reports
- **Owner:** sonnet · **Depends on:** P1-06 · **Read first:** `docs/04` A4, `docs/10` §5
- **Files:** `src/reval/uq/domain.py`, `docs/10-interfaces.md` §5 (add the signature), `tests/unit/uq/test_domain_combine.py`
- **Spec:** `combine_reports(parts: Mapping[str, DomainReport]) -> dict[str, Any]` returns `{"inside": all(p.inside), "first_failing_part": <first name in sorted order with inside False> | None, "parts": {name: report.to_dict()}}`.
  This is what goes into `EvidenceResult.domain_report` when there are several gates (drive map + model). An empty mapping → `ValueError`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/uq/test_domain_combine.py`: one failing part → `inside=False` and named; the output is JSON-serializable (passes `canonical_json`).

## P4-03 — Motor ML producers (conformal + AD evidence)
- **Owner:** sonnet · **Depends on:** P4-02, P1-13, P2-13 · **Read first:** `docs/05` §3, §7, `docs/10` §5 (producer rule), §12 (`producers.py`)
- **Files:** `examples/motor_thermal/motor/producers.py`, `examples/motor_thermal/reval.yaml`, `tests/unit/motor/test_producers_ml.py`
- **Spec:**
  1. Declare the artifacts `uq_tpm_<m>` / `uq_tsw_<m>` (model, `derived_from: [tpm_<m> | tsw_<m>, measures, splits]`), produced by P1-13's `scripts/calibrate.py`. This task does **not** recalibrate.
  2. Register `predict_pm_peak_<m>` and `predict_sw_peak_<m>` for m ∈ {ridge, hgb, mlp}: `kind=ML_PREDICTION`, `predictors=["tpm_<m>"]` (or `tsw_<m>`), and
     `depends_on` = the model, its uq artifact, `drive_map`, and `cooling#/flow_scale` (a pointer, **no tolerance**, so a flow change fails closed).
  3. Result: `interval` = the `PeakConformal` interval on the trajectory's peak, for the subject's length class. If it is `None`, emit `interval=None`, `point=<pred>`, and `uncertainty_kind="none"` (`docs/10` §5).
     `in_domain` = drive-map AD **and** model AD on the trajectory features, with `domain_report = combine_reports({"drive_map": …, "model": …})`.
     `Scope.box` = the trajectory's bounding box over (torque, motor_speed, coolant, ambient).
- **Acceptance:**
  - Data tests (`.venv/Scripts/python -m pytest -m data tests/unit/motor/test_producers_ml.py`): a recorded test cycle is in domain; a synthetic cycle at coolant 95 °C is out of domain with `coolant` listed. Without data, these are skipped.
  - A data-free unit test with stub artifacts checks the `interval=None` path.
- **Pitfalls:** use `ctx.load` for every artifact (undeclared reads raise). Temperatures are absolute °C. Interval half-widths are K.

## P4-04 — ML gate tests (verdicts and status)
- **Owner:** sonnet · **Depends on:** P2-09, P2-12 · **Read first:** `docs/03` §2–3, `docs/10` §4.4–4.5
- **Files:** `tests/unit/core/test_verdicts_ml.py`, `tests/property/test_ml_gate.py`
- **Spec:** no new engine code is expected. If a test exposes a gap, fix it in `src/reval/core/verdicts.py` per `docs/10` §4.4. Tests:
  - Out-of-domain ML evidence is always INCONCLUSIVE with `OUT_OF_DOMAIN`, whatever the interval (a property over random intervals).
  - GE/LE symmetry.
  - Boundary inclusivity: `hi == L` → PASS; `lo == L < hi` → not FAIL.
  - An out-of-domain ML item can never be the ML conjunct of a satisfied medium clause.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core tests/property` passes.

## P4-05 — Planning problem: obligations, candidates, independence
- **Owner:** sonnet · **Depends on:** P2-09 · **Read first:** `docs/04` A7, `docs/10` §2 (`plan.py`), §4.6
- **Files:** `src/reval/core/planner.py` (part 1), `tests/unit/core/test_planner_problem.py`
- **Spec:** `CRITICALITY_WEIGHT` and `build_problem(snapshot, assessments, items, *, available, known_out_of_domain=frozenset())`, exactly as §4.6:
  - Claims with status STALE or INCONCLUSIVE are planned; every conjunct becomes an obligation (nothing is dropped).
  - Reuse candidates `existing:<id>` (cost 0).
  - New-run candidates, excluding (P, S) pairs that already have **FRESH_EXACT** evidence at this snapshot (CARRY_FORWARD and FRESH_OUT_OF_SCOPE items stay rerunnable), and excluding ML for `known_out_of_domain` **regardless of `in_domain`**.
  - **Lost-fail obligations:** for every non-superseded lost-fail item of a planned claim (`docs/03` §3 rule 3), add a mandatory obligation "rerun producer(item) on S" alongside the clause. A clause covered by `existing:` evidence does not restore the claim while such an obligation is open.
  - `incompatible` tuples for independence.
  - Deterministic ordering.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_planner_problem.py` with hand-built fixtures:
  - One measurement candidate on a subject satisfies obligations of two claims on that subject.
  - A fresh PASS item appears as `existing:` with cost 0.
  - An unavailable producer yields no candidate; a known-out-of-domain ML producer yields no candidate.
  - ML and physics sharing a predictor produce an `incompatible` entry.
  - A carried-forward `sim_temp` item on S1 still yields a `sim_temp@S1` new-run candidate. Only a FRESH_EXACT item blocks it.
  - A STALE (lost fail) claim with a clause covered by `existing:` PASS evidence still gets a mandatory rerun obligation for the invalidated FAIL item's producer. With budget 0 it is `deferred`, never restored at cost 0.

## P4-06 — CP-SAT min-cost planner
- **Owner:** sonnet · **Depends on:** P4-05 · **Read first:** `docs/04` A7, `docs/10` §4.6 (ILP)
- **Files:** `src/reval/core/planner.py` (part 2), `tests/unit/core/test_planner_ilp.py`
- **Spec:** `plan(problem, planner="ilp", objective="min_cost", max_time_s=10.0) -> RevalidationPlan`, exactly as §4.6:
  - Variables `z_j`, `x_{j,o}`, `y_{c,k}`, `u_c`. Integer costs ×100, `M = 1 + Σ cost_int`, integer weights.
  - `num_workers=1`, `random_seed=0`.
  - `solver_status` is recorded; `FEASIBLE` → `reproducible=False`.
  - `unrestorable` is computed independently of the budget. `PlannedRun`s are produced for new-run candidates only.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_planner_ilp.py`:
  - On 200 seeded random instances (≤ 10 candidates, ≤ 4 claims), the cost equals **brute force over all candidate subsets**, and every result has `solver_status == "OPTIMAL"`.
  - The same input gives byte-identical plan JSON.
  - Incompatible pairs are never both used for one clause.
- **Pitfalls:** `ortools` is imported only in this module. Don't leak solver objects into returned models.

## P4-07 — Budgeted variant (max-restored) + `deferred`
- **Owner:** sonnet · **Depends on:** P4-06 · **Read first:** `docs/10` §4.6 (`max_restored`, `unrestorable` vs `deferred`)
- **Files:** `src/reval/core/planner.py`, `tests/unit/core/test_planner_budget.py`
- **Spec:** `objective="max_restored"` requires `budget` (otherwise `ValueError`). Use the single integer objective of §4.6. Claims left uncovered but restorable go to `deferred`. Claims impossible at any budget go to `unrestorable`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_planner_budget.py`: the brute-force comparison as in P4-06; monotonicity (a larger budget never restores less weight); with budget 0, every restorable claim is `deferred`, not `unrestorable`.

## P4-08 — Greedy and "all" planners
- **Owner:** sonnet · **Depends on:** P4-06 · **Read first:** `docs/10` §4.6 (greedy, all)
- **Files:** `src/reval/core/planner.py`, `tests/unit/core/test_planner_greedy.py`
- **Spec:** `planner="greedy"` and `planner="all"` exactly as §4.6. Greedy respects `incompatible` and prunes redundant runs in descending cost order. `solver_status` is `"GREEDY"` / `"ALL"`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_planner_greedy.py`: greedy cost ≥ ILP cost on every random instance; greedy covers every claim the ILP covers; "all" cost = the sum of the selected new-run candidates.

## P4-09 — `Project.plan` + `reval plan`
- **Owner:** sonnet · **Depends on:** P4-07, P4-08, P3-06 · **Read first:** `docs/09` (`plan`), `docs/10` §10
- **Files:** `src/reval/services/project.py` (`Project.plan`), `src/reval/cli/main.py`, `src/reval/cli/render.py`, `tests/integration/test_cli_plan.py`
- **Spec:** `reval plan [--budget N] [--planner ilp|greedy|all] [--format table|json]`. `--budget` implies `objective="max_restored"`. `available` and `known_out_of_domain` are computed as in
  `docs/10` §10. The plan is stored, and the command prints the runs, costs, discharged obligations, `unrestorable`, and `deferred`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_cli_plan.py` on the mini project after a `/load/scale` change: the table is deterministic; `--format json` validates as
  `RevalidationPlan`; `--budget 0` lists every restorable claim as deferred.

## P4-10 — Job runner + `reval run --plan/--only`
- **Owner:** sonnet · **Depends on:** P4-09, P2-18 · **Read first:** `docs/09` (`run`), `docs/10` §8 (jobs), §10
- **Files:** `src/reval/services/jobs.py`, `src/reval/services/project.py` (`Project.run_plan`), `src/reval/cli/main.py`, `tests/integration/test_cli_run.py`
- **Spec:** an in-process runner executes the planned runs in plan order. It writes one `Job` per run via `put_job`, moving through `update_job_state` (queued → running → succeeded/failed),
  and appends evidence. A failing run marks its job failed and the runner continues. `reval run [--all | --plan ID] [--only PRODUCER]`. `--all` (P2-18) keeps working, and `--plan latest` is accepted.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_cli_run.py` on the mini project: `diff → plan → run --plan latest` turns a STALE claim SUPPORTED; a producer that raises
  gives a failed job and no evidence, and the claim stays STALE.
- **Pitfalls:** evidence is append-only. Never update an evidence row.

## P4-11 — Re-assessment loop + invariant I6
- **Owner:** sonnet · **Depends on:** P4-10 · **Read first:** `docs/03` §5 (I6)
- **Files:** `src/reval/services/project.py`, `tests/property/test_plan_soundness.py`
- **Spec:** after `run_plan`, re-assess automatically (a new assessment batch, D18) and return or print before/after statuses. I6 property test: with a fake registry whose runs always return
  decisive PASS evidence, every planned claim not in `unrestorable` or `deferred` ends SUPPORTED. The strategy must include lost-fail claims, and the property must hold for them
  too (their mandatory rerun obligations supersede the invalidated FAIL items).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/property/test_plan_soundness.py` passes under the `ci` profile.

## P4-12 — Canonical report JSON
- **Owner:** sonnet · **Depends on:** P4-11 · **Read first:** `docs/09` "Report format", `docs/10` §10 (report hashing, clock)
- **Files:** `src/reval/report/{__init__,model,build}.py`, `tests/golden/test_report_json.py`, `tests/golden/report_mini.json`
- **Spec:** a `Report` pydantic model with exactly the `docs/09` fields (including the plan's `deferred`). `report_hash = content_id(report, exclude={"report_hash", "report_id", "created_at"})`
  and `report_id = report_hash[:16]` (D19). `created_at` comes from the clock injected into `Project.open`, so tests pass a fixed clock. Reports are stored with `put_report`.
  **The disclaimer string is a module constant and mandatory.**
- **Acceptance:** `.venv/Scripts/python -m pytest tests/golden/test_report_json.py`: the golden file matches with a fixed clock; two different clock values give the **same** `report_hash`.

## P4-13 — Markdown + HTML rendering, `reval report`
- **Owner:** sonnet · **Depends on:** P4-12 · **Read first:** `docs/09`, AGENTS rule 9
- **Files:** `src/reval/report/render.py`, `src/reval/report/templates/report.html.j2`, `src/reval/report/templates/report.md.j2`, `pyproject.toml` (add `jinja2>=3.1` to the main
  dependencies; ship the templates as package data), `src/reval/cli/main.py`, `tests/golden/test_report_render.py`
- **Spec:** `reval report [--html] [--out PATH]`. The HTML is self-contained (inline CSS, no external requests). Every status is shown with an icon **and** text. The disclaimer goes at the top.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/golden/test_report_render.py`:
  - The Markdown matches its golden file.
  - The HTML contains the disclaimer and every claim id.
  - No `http` URL appears in the HTML.
  - A test greps the templates and fails on "safe", "certified", or "guarantee".

## P4-14 — `reval explain CLAIM`
- **Owner:** sonnet · **Depends on:** P4-12 · **Read first:** `docs/09` (`explain`)
- **Files:** `src/reval/report/explain.py`, `src/reval/cli/main.py`, `tests/golden/test_explain.py`
- **Spec:** a deterministic text tree: claim → status → reasons → satisfied/failed clauses → evidence (verdict, freshness, interval, recorded verdict, producer) → dependencies (`selector@hash[:8]`).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/golden/test_explain.py` matches the golden output for `C-S1-TEMP` after a `/load/scale` change.

## P4-16 — `reval init` and `reval graph`
- **Owner:** sonnet · **Depends on:** P2-17, P2-07 · **Read first:** `docs/09` (`init`, `graph`), `docs/10` §4.1 (`to_json`)
- **Files:** `src/reval/cli/main.py`, `src/reval/cli/templates/reval.yaml.tmpl`, `tests/integration/test_cli_init_graph.py`
- **Spec:**
  - `reval init` writes a commented starter `reval.yaml` (version, project, quantities, one example of each entity, all commented out where invalid) and creates `.reval/`.
    It refuses to overwrite an existing manifest (exit 3).
  - `reval graph [--claim ID] --out graph.json` writes `EvidenceGraph.to_json(focus)`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_cli_init_graph.py`: `init` in an empty `tmp_path` produces a manifest that `load_manifest` accepts; a second `init` exits 3;
  `graph --claim C-SHAFT` on the mini project contains no `field:params#/load/scale` node.

## P4-15 — M4 demo script + review
- **Owner:** sonnet+human-review · **Depends on:** P4-03, P4-13, P4-14, P3-08 · **Read first:** `docs/07` M4
- **Files:** `examples/motor_thermal/demo_full.sh`, `examples/motor_thermal/demo_full.ps1`, `tests/integration/test_demo_full.py`
- **Spec:** scripted: baseline snapshot + `run --all` → commit a coolant change → `reval diff HEAD~1 HEAD` → `plan` → `run --plan latest` → `report --html`.
- **Acceptance:** `tests/integration/test_demo_full.py` (marked `data` and `slow`) runs the script and asserts exit 0 and that the HTML report exists. NEEDS HUMAN: check the report wording and numbers, then update the M4 status in `docs/07-roadmap.md`.
