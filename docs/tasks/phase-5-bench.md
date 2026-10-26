# Phase 5 — ReValBench (roadmap weeks 19–23, milestone M5)

**Read first for every task:** `AGENTS.md`, `docs/06-evaluation.md` (all of it), `docs/05-motor-domain.md` §8, `docs/10-interfaces.md`.
**Phase goal (M5 DoD):** `python -m bench.run --config bench/configs/full.yaml` regenerates every figure and table from scratch, and the results are archived with hashes.
Conventions: see the header of `phase-0-foundations.md`.

**Rules specific to this phase:**
- Benchmark code lives in `bench/` (a package at the repo root, importable because `"."` is on the pytest path). It may import `reval` and `motor`.
  `reval` and `motor` must never import `bench` (architecture test in P5-05).
- Benchmark tests live in `tests/bench/`, never inside `bench/`.
- Every scenario is reproducible from `(config hash, seed, scenario index)`. **Common random numbers:** all noise uses
  `np.random.default_rng(int(sha256(f"{scenario_id}|{producer_id}|{subject_id}").hexdigest()[:8], 16))`, identical for S and S′ and for every method (`docs/06` §2).
- Tier A and Tier B results are stored and reported **separately**. Never pool them. Tier A truth comes only from recorded **test** cycles. `reserve` profiles are never subjects.
- Benchmarks contain **no waivers**.

---

## P5-02 — Bench harness: throwaway clones + scenario commits
- **Owner:** sonnet · **Depends on:** P3-06, P4-10 · **Read first:** `docs/06` §2, ADR 0005
- **Files:** `bench/__init__.py`, `bench/harness/__init__.py`, `bench/harness/workspace.py`, `tests/bench/test_workspace.py`
- **Spec:** `Workspace.create(base_repo: Path, tmp_root: Path, data_cache: Path | None) -> Workspace` runs `git clone --local` of the project into `tmp_root/<scenario_id>` and copies
  (hardlinks where possible) `data/` and `models/` from the cache. It also has `commit(message) -> str` (the rev), `run_reval(args) -> subprocess.CompletedProcess`
  (`[sys.executable, "-m", "reval.cli.main", ...]`), and `cleanup()`. Fixed `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env and dates make commits deterministic.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_workspace.py`: a workspace from a git-initialized copy of `tests/fixtures/mini_project` commits a `/load/scale` change, and
  `reval diff HEAD~1 HEAD --format json` shows one `FIELD_CHANGED`. The user's real repo is never touched.

## P5-03 — Scenario model + generator, Tier A part 1 (T1–T5)
- **Owner:** sonnet · **Depends on:** P5-02, P4-03 · **Read first:** `docs/06` §2 change taxonomy
- **Files:** `bench/scenarios/{__init__,model,generate,tier_a}.py`, `tests/bench/test_generate.py`, `tests/bench/test_tier_a.py`
- **Spec:**
  1. `Scenario` (frozen pydantic): `id`, `change_type` (T1…T12), `tier` (A/B), `seed`, `base_snapshot` (cluster id for the bootstrap), `params`, and `apply` (the name of a registered applier).
  2. `generate(config, seed) -> list[Scenario]` is deterministic and spreads scenarios over ≥ 30 base snapshots (`docs/06` §2).
  3. Appliers edit the workspace and recompute what an engineer would recompute, using the project's scripts:
     - **T1:** append an in-envelope `reserve` profile, then retrain and recalibrate.
     - **T2:** append an envelope-expanding profile.
     - **T3:** a sensor-offset correction of ±0.5–3 K on one profile's `pm` column.
     - **T4:** a hyperparameter change or a model swap.
     - **T5:** a requirement limit change of ±2–10 K.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_generate.py tests/bench/test_tier_a.py`: the same seed gives identical lists. Each applier is unit-tested on the mini project
  (where the change type applies) or with motor data under the `data` marker.

## P5-04 — Tier A part 2 (T6, T10, T11)
- **Owner:** sonnet · **Depends on:** P5-03 · **Read first:** `docs/06` §2
- **Files:** `bench/scenarios/tier_a.py`, `tests/bench/test_tier_a_part2.py`
- **Spec:**
  - **T6:** an assumption range change.
  - **T10:** an unrelated change (README, shaft value) that only affects the shaft claim.
  - **T11:** a producer code change in two flavors: a behavior-preserving refactor (rename a local variable) and a behavior-changing fix (scale the output by 1.01).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_tier_a_part2.py`: T10 on the mini project affects only `C-SHAFT` or nothing; both T11 flavors invalidate (fail-closed).

## P5-05 — Tier B virtual world model
- **Owner:** sonnet+human-review · **Depends on:** P1-08 · **Read first:** `docs/05` §8, `docs/06` §7
- **Files:** `bench/world/{__init__,model,calibrate}.py`, `tests/bench/test_world.py`, `tests/unit/test_architecture.py` (extend it)
- **Spec:** a thermal model structurally different from the design-time LPTN: ≥ 6 nodes, temperature-dependent conductances, its own flow–conductance relation, and an injected
  model-form error term (a smooth function of speed). Calibrated on **train + reserve only** (R7). API: `World.simulate(trajectory, physical_params) -> pd.DataFrame` (noise-free) and
  `World.measure(trajectory, physical_params, rng) -> pd.DataFrame` (adds `N(0, σ_sensor)`). `physical_params` has `R_ic_scale`, `coolant_flow_scale`, and `sensor_offset`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_world.py tests/unit/test_architecture.py`:
  - The node count and parameter names differ from the design LPTN.
  - The architecture test fails if `reval/` or `motor/` imports `bench`.
  - With the `data` marker, world MSE on test profiles is reported (it doesn't need to beat the LPTN).
  - NEEDS HUMAN: is the world plausible?

## P5-18 — Tier B base snapshots: ML retrained on world trajectories
- **Owner:** sonnet · **Depends on:** P5-05, P4-03 · **Read first:** `docs/06` §7 (R7), `docs/05` §8
- **Files:** `bench/world/base.py`, `tests/bench/test_world_base.py`
- **Spec:** `build_tier_b_base(workspace, world, physical_params, seed) -> None` replaces the measured temperatures of the train/calib/test input profiles with world trajectories,
  then reruns `scripts/train.py`, `scripts/calibrate.py`, and `scripts/calibrate_lptn.py` in the workspace and writes the lock. ML and truth then refer to the same plant.
  It also writes `bench_measurements.json` (`{subject_id: {quantity: measured_peak}}`, from `World.measure` with common random numbers) **outside** the declared artifacts.
  For Tier B, `motor.producers.bench_measure` reads that table when the env var `REVAL_BENCH_MEASUREMENTS` is set (add this branch to `examples/motor_thermal/motor/producers.py`).
  The table is deliberately undeclared: it is the "physical world", so T9 drift stays invisible.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_world_base.py` on a tiny synthetic world: the retrained model fits the world data better than the original; the measurement table is deterministic under the common-random-number seed.

## P5-06 — Tier B scenarios (T6-B, T7, T8, T9, T12)
- **Owner:** sonnet · **Depends on:** P5-18, P5-04 · **Read first:** `docs/06` §2
- **Files:** `bench/scenarios/tier_b.py`, `tests/bench/test_tier_b.py`
- **Spec:**
  - **T7:** a small declared change: `cooling#/flow_scale` −2…−8 %, applied to both the params file and the world.
  - **T8:** a large declared change: −15…−35 %.
  - **T9:** undeclared degradation: world `R_ic_scale` 1.1–1.4 with **no file change**, only a regenerated measurement table.
  - **T12:** compound: 2–3 random changes from the applicable set, seeded.
  - **T6-B:** an assumption change in Tier B.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_tier_b.py`: for T9, the scenario's change set is empty (asserted); for T7/T8, the params diff matches the world change.

## P5-07 — Evidence oracle (B0 rerun-all)
- **Owner:** sonnet · **Depends on:** P5-02 · **Read first:** `docs/06` §2 "Ground truth"
- **Files:** `bench/oracles/{__init__,evidence}.py`, `tests/bench/test_evidence_oracle.py`
- **Spec:** in the post-change workspace, run every producer for every claim subject (cached by `(producer_id, code_hash, inputs hash, subject)`) and assess. Return
  `{claim_id: (status, evidence values)}`. Truly affected = the B0 status differs between S and S′, **or** some evidence value referenced by **any clause of Π_c in S or S′** moved by more than ε.
  ε = `0.1 · median q̂` per target, taken from the config (pre-registered).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_evidence_oracle.py` on the mini project: hand-labelled cases, including a claim affected only through an unused clause's evidence.

## P5-08 — Truth oracles
- **Owner:** sonnet · **Depends on:** P5-05, P5-07 · **Read first:** `docs/06` §2
- **Files:** `bench/oracles/truth.py`, `tests/bench/test_truth_oracle.py`
- **Spec:** returns `{claim_id: bool | None}`. Tier A: the measured peak on recorded **test** cycles, taken from the **S′** data. Every other subject gets `None` and is excluded from
  UAR_truth in Tier A. Tier B: the world's noise-free peak for every subject.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_truth_oracle.py`: fixture cases for both tiers; the share of `None` is returned for reporting.

## P5-09 — Baselines B1–B4
- **Owner:** sonnet · **Depends on:** P5-07 · **Read first:** `docs/06` §4
- **Files:** `bench/baselines/{__init__,file_level,ood_only,naive,random_budget}.py`, `tests/bench/test_baselines.py`
- **Spec:** each baseline has `select_runs(pre_state, post_workspace) -> list[tuple[str, str]]` (producer_id, subject_id) and executes through the same runner.
  - **B1:** whole-file hashes, an independent tiny implementation rather than ReVal's field hashing.
  - **B2:** keeps old evidence and reruns ML only where the subject is out of domain under the new model.
  - **B3:** runs nothing.
  - **B4:** random runs up to ReVal's cost, using common random numbers.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_baselines.py` on the mini project: for a single-field change, B1 reruns strictly more than ReVal; B3 costs 0; B4 is deterministic.

## P5-10 — Metrics
- **Owner:** sonnet · **Depends on:** P5-07, P5-08, P5-09 · **Read first:** `docs/06` §3
- **Files:** `bench/analysis/{__init__,metrics}.py`, `tests/bench/test_metrics.py`
- **Spec:** implement exactly the `docs/06` §3 definitions:
  - impact recall, precision, and F2;
  - UAR_evidence, UAR_truth, and UAR*, as **ratios of sums**;
  - decision coverage;
  - cost ratio, the paired log cost ratio, cost per claim decided, and false-alarm cost (same ε);
  - reproducibility and optimality gap.
  WAIVED is excluded. A zero denominator contributes 0/0 to the pooled sums and is never averaged as NaN. Input: a tidy DataFrame with one row per (scenario, method, claim),
  including `change_type`, `tier`, and `base_snapshot`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_metrics.py`: hand-computed fixtures with ≥ 1 test per metric, including a scenario with zero accepted claims.

## P5-11 — Runner, cache, smoke config
- **Owner:** sonnet · **Depends on:** P5-10, P5-04, P5-06 · **Read first:** `docs/06` §2, `docs/08` R8
- **Files:** `bench/run.py`, `bench/cache.py`, `bench/configs/smoke.yaml`, `bench/configs/full.yaml`, `tests/bench/test_run_smoke.py`
- **Spec:** `python -m bench.run --config X [--jobs N]` runs scenarios in parallel with joblib and writes `bench/results/<config_hash>/rows.parquet`, `manifest.json` (git rev, config hash,
  package versions, seeds), and `rows.sha256`. A producer-result cache is keyed by `(producer code hash, input hash)`.
- **Acceptance:** `tests/bench/test_run_smoke.py` (marked `slow`) runs a 2-scenario mini-project config and checks that a rerun hits the cache and gives an identical `rows.sha256`.
  NEEDS HUMAN: `python -m bench.run --config bench/configs/smoke.yaml` (≈ 2 scenarios per type, motor data) finishes in < 15 min on the laptop.

## P5-12 — Statistics: stratified cluster bootstrap + non-inferiority
- **Owner:** sonnet · **Depends on:** P5-10 · **Read first:** `docs/06` §6, `docs/research/preregistration.md`
- **Files:** `bench/analysis/stats.py`, `tests/bench/test_stats.py`
- **Spec:**
  - `stratified_cluster_bootstrap(df, metric_fn, *, strata="change_type", cluster="base_snapshot", n=10_000, seed=0) -> tuple[float, float, float]` (estimate, lo, hi; percentile).
    It resamples clusters with replacement **within each stratum** and recomputes ratio metrics from pooled sums in each resample.
  - `paired_difference_ci(...)`.
  - `non_inferior(upper_bound: float, delta: float) -> bool`, using the one-sided 97.5 % bound.
  - `holm(pvalues: Mapping[str, float], alpha=0.05) -> dict[str, bool]`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_stats.py`: a synthetic case with a known CI (within tolerance); strata are never mixed; Holm matches a hand example; seeded runs are deterministic.

## P5-13 — Ablation settings plumbing (A1, A2, A3, A6, A7)
- **Owner:** sonnet · **Depends on:** P5-11 · **Read first:** `docs/06` §5, ADR 0001
- **Files:** `src/reval/domain/settings.py` (core may import domain; `reval.services` re-exports it), `src/reval/core/freshness.py`, `src/reval/services/project.py`, `docs/10-interfaces.md` (document the new keyword-only `settings` parameters),
  `bench/configs/ablations/{a1_no_field_selectors,a2_no_carry_forward,a3_no_scope,a6_greedy,a7_kappa}.yaml`, `tests/unit/core/test_ablation_flags.py`
- **Spec:** `ReValSettings` (frozen pydantic) with `field_selectors: bool = True`, `carry_forward: bool = True`, `scope_freshness: bool = True`, `planner: Literal["ilp", "greedy"] = "ilp"`,
  and `kappa_override: float | None = None`. The flags reach core **as arguments**: `classify_evidence(..., *, settings=DEFAULT_SETTINGS)` treats every dep as whole-artifact (A1),
  disables tolerance excuses (A2) or row excuses (A3), and replaces `safety_factor` (A7). The defaults reproduce the main method exactly.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_ablation_flags.py`: each flag changes the outcome on a crafted mini case; defaults are identical to no settings; every ablation config runs in smoke mode (`slow`).
- **Pitfalls:** the core stays pure. No global state, no environment reads in core.

## P5-19 — Uncertainty and AD ablations (A4, A5, A8)
- **Owner:** sonnet · **Depends on:** P5-13, P4-01 · **Read first:** `docs/06` §5, `docs/04` A4–A5
- **Files:** `src/reval/uq/cqr.py` (CQR / normalized scores, documented in `docs/10` §5), `src/reval/domain/settings.py` (`ad_mode`, `uncertainty`), `src/reval/sdk/context.py` (`Context.settings` property, per `docs/10` §7), `examples/motor_thermal/motor/producers.py` (read
  `ctx.settings`), `bench/configs/ablations/{a4_ad_modes,a5_fixed_margin,a8_cqr}.yaml`, `tests/unit/uq/test_cqr.py`
- **Spec:** `ad_mode: Literal["strict", "relaxed", "off"]` and `uncertainty: Literal["conformal", "fixed_margin", "cqr"]`. `off` and `fixed_margin` are **bench-only**: they're reachable only
  when `REVAL_BENCH=1` is set, and AGENTS.md is updated to say they're forbidden for real use. CQR follows Romano et al. 2019 on peaks.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/uq/test_cqr.py tests/unit/core/test_ablation_flags.py`: CQR coverage on synthetic heteroscedastic data is ≥ 1−α−0.05; `ad_mode="off"` without `REVAL_BENCH=1` raises.

## P5-14 — Cost sensitivity
- **Owner:** sonnet · **Depends on:** P5-11 · **Read first:** `docs/06` §3 (cost)
- **Files:** `bench/configs/cost_sensitivity.yaml`, `bench/run.py` (`cost_profile` tag), `tests/bench/test_cost_profile.py`
- **Spec:** bench cost ∈ {20, 100, 500}, with other costs fixed. Re-plan only, reusing cached evidence.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_cost_profile.py`: rows are tagged with `cost_profile`, and a higher bench cost never increases the number of bench runs chosen.

## P5-20 — RQ4 optimizer experiment (Tier B, 2 × 2)
- **Owner:** sonnet · **Depends on:** P5-08, P5-18, P1-11 · **Read first:** `docs/06` §1 RQ4, §6 (H3 design)
- **Files:** `bench/experiments/rq4.py`, `bench/configs/rq4.yaml`, `tests/bench/test_rq4.py`
- **Spec:** {O1, O3} × {point-acceptance, ReVal-gated acceptance}, with N ≥ 50 optimizer runs per cell (DE seeds × limit levels), in Tier B. It writes rows with `cell`, `accepted`, and `truth` from the world.
  Primary contrast: gated vs point on O1 optima.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_rq4.py` on a stub world: every cell gets N rows, and point-acceptance accepts every O1 optimum by construction.

## P5-17 — Pilot run on development seeds
- **Owner:** sonnet+human-review · **Depends on:** P5-11, P5-12, P5-13, P5-19, P5-14, P5-20 · **Read first:** `docs/06` §6 timeline
- **Files:** `bench/configs/pilot.yaml`, `docs/log/<date>-pilot.md`
- **Spec:** run every method, ablation, and RQ4 on **development seeds only** (recorded in `pilot.yaml`, never reused). Measure the wall-clock per scenario and propose instance counts,
  ε per target (0.1 · median q̂), δ (absolute and relative to pilot UAR_truth(B0)), and the predicted UAR_truth floor (≈ α). Write a proposal into the log, with numbers from the script output only.
- **Acceptance:** the pilot results directory exists with `rows.sha256`. NEEDS HUMAN: review the proposal.

## P5-01 — Pre-registration (HUMAN GATE)
- **Owner:** human · **Depends on:** P5-17 · **Read first:** `docs/research/preregistration.md`, `docs/06` §6
- **Files:** `docs/research/preregistration.md`
- **Spec:** fill in every field from the pilot proposal: H1 (four parts), H2, H3, δ, ε, scenario counts, number of base snapshots, final-run seeds (fresh), declared limits, α, κ, AD thresholds,
  costs, and exclusion rules. Commit with the message `docs(research): pre-registration` at the **end of week 21**. **No final run (P5-16) may start before this commit exists.**
- **Acceptance:** `git log --grep "docs(research): pre-registration"` finds the commit. NEEDS HUMAN: the supervisor has seen it.

## P5-15 — Figures and tables (scripted)
- **Owner:** sonnet · **Depends on:** P5-12, P5-13, P5-19, P5-14, P5-20 · **Read first:** `docs/06` §3, §6, `dataviz` skill
- **Files:** `bench/analysis/figures.py`, `bench/analysis/tables.py`, `tests/bench/test_figures.py`. The output goes to `bench/results/<hash>/figures/` and `tables/*.tex`.
- **Spec:** the figures and tables, with Tier A and Tier B in separate panels (colorblind-safe, labelled units):
  1. cost ratio vs UAR_truth per method and change type;
  2. impact recall/precision/F2 per change type;
  3. the ablation table (A1–A8);
  4. the κ curve;
  5. conformal coverage per length class;
  6. the RQ4 2 × 2;
  7. cost sensitivity;
  8. the H1 four-part result table.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/bench/test_figures.py` regenerates every output from a tiny fixture results directory. `python -m bench.analysis.figures --results bench/results/<hash>` works. No hand-edited numbers.

## P5-16 — Final run + archive (HUMAN REVIEW)
- **Owner:** sonnet+human-review · **Depends on:** P5-01, P5-15 · **Read first:** `docs/research/preregistration.md`
- **Files:** `docs/log/<date>-final-run.md`, `docs/research/preregistration.md` (§Deviations only)
- **Spec:** run `full.yaml`, the ablations, cost sensitivity, and RQ4 on the **pre-registered fresh seeds**. Record the result hashes in `docs/log/`. Any deviation from the pre-registration goes into §Deviations.
- **Acceptance:** every `rows.sha256` is listed in the log. NEEDS HUMAN: review the headline numbers per change type before anything goes into the paper.
