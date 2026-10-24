# Phase 5 — ReValBench (roadmap weeks 19–23, milestone M5)

**Read first for every task:** `AGENTS.md`, `docs/06-evaluation.md` (all of it), `docs/05-motor-domain.md` §8, `docs/10-interfaces.md`.
**Phase goal (M5 DoD):** `python -m bench.run --config bench/configs/full.yaml` regenerates every figure and table from scratch. Results are archived with hashes.

**Rules specific to this phase:**
- Benchmark code lives in `bench/`. It may import `reval` and `motor`. `reval` must never import `bench`.
- Every scenario is reproducible from `(config hash, seed, scenario index)`.
- Tier A and Tier B results are stored and reported **separately**. Never pool them.

---

## P5-01 — Pre-registration (HUMAN GATE)
- **Owner:** human · **Depends on:** P4-15
- **Files:** `docs/research/preregistration.md`
- **Spec:** fill in every field: hypotheses H1–H3, δ, scenario counts per type, seeds, declared limits, α, κ, AD thresholds, costs, exclusion rules. Commit with the message `docs(research): pre-registration`. **No full benchmark run (P5-16) may start before this commit exists.** Smoke runs (P5-11) are allowed.
- **Acceptance:** the commit exists. The supervisor has seen it.

## P5-02 — Bench harness: throwaway clones + scenario commits
- **Owner:** sonnet · **Depends on:** P4-15
- **Files:** `bench/__init__.py`, `bench/harness/workspace.py`, `bench/tests/test_workspace.py`
- **Spec:**
  1. `Workspace.create(base_repo: Path, tmp_root: Path, data_cache: Path) -> Workspace`: `git clone --local` the reference project into `tmp_root/<scenario_id>`, and symlink or copy (on Windows, copy with hardlinks if possible) `data/` and `models/` from the cache.
  2. `ws.commit(message) -> str` (rev). `ws.run_reval(args) -> CompletedProcess` (subprocess, captured). `ws.cleanup()`.
  3. Every scenario: base commit (with `reval.lock.json`) → apply the change → `reval snapshot --write` → commit.
- **Acceptance:** a test creates a workspace from `tests/fixtures/toy_project`, commits a param change, and `reval diff HEAD~1 HEAD --format json` shows one `FIELD_CHANGED`.
- **Pitfalls:** set `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env and fixed dates so commits are deterministic. Never touch the user's real repo.

## P5-03 — Scenario model + generator, Tier A part 1 (T1–T5)
- **Owner:** sonnet · **Depends on:** P5-02
- **Files:** `bench/scenarios/model.py`, `bench/scenarios/generate.py`, `bench/scenarios/tier_a.py`, `bench/tests/test_generate.py`
- **Spec:**
  1. `Scenario` (frozen pydantic): `id`, `change_type` (T1…T12), `tier` (A/B), `seed`, `params`, `apply: str` (registered function name).
  2. `generate(config, seed) -> list[Scenario]`, deterministic.
  3. Change appliers (each edits files in the workspace, then retrains/recomputes as the real engineer would via the project's scripts):
     - T1 append an in-envelope `reserve` profile → retrain the model, recalibrate.
     - T2 append an envelope-expanding profile.
     - T3 sensor-offset correction on one profile's `pm` column (+/− 0.5–3 K).
     - T4 hyperparameter change or model swap.
     - T5 requirement limit change ±2–10 K.
- **Acceptance:** `generate` with the same seed → identical lists. Each applier is unit-tested on the toy project (or with motor data under the `data` marker).

## P5-04 — Tier A part 2 (T6, T10, T11)
- **Owner:** sonnet · **Depends on:** P5-03
- **Files:** `bench/scenarios/tier_a.py`
- **Spec:** T6 assumption range change. T10 unrelated change (README, shaft drawing value) → only the shaft claim is affected. T11 producer code change in two flavors: a behavior-preserving refactor (rename a local variable) and a behavior-changing fix (scale the output by 1.01).
- **Acceptance:** unit tests per applier. T10 on the toy project yields zero affected thermal claims.

## P5-05 — Tier B virtual world model
- **Owner:** sonnet+human-review · **Depends on:** P1 LPTN
- **Files:** `bench/world/model.py`, `bench/world/calibrate.py`, `bench/tests/test_world.py`
- **Spec:** a structurally different thermal model from the design-time LPTN: ≥ 6 nodes, temperature-dependent conductances, plus an injected model-form error term (a smooth function of speed). Calibrate it on **all** profiles. API: `World.simulate(trajectory, physical_params) -> temps`, `World.measure(trajectory, rng) -> temps + N(0, σ_sensor)`. `physical_params` include `R_ic_scale`, `coolant_flow_scale`, `sensor_offset`.
- **Acceptance:** world MSE on test profiles is reported (it doesn't need to beat the LPTN). The structure-difference test asserts that the node count and parameter names differ from the design LPTN. Human review: is the world plausible?
- **Pitfalls:** the design-time models must never read world parameters. Add an architecture test: `motor/` must not import `bench.world`.

## P5-06 — Tier B scenarios (T6-B, T7, T8, T9, T12)
- **Owner:** sonnet · **Depends on:** P5-05, P5-04
- **Files:** `bench/scenarios/tier_b.py`
- **Spec:** T7 small declared parameter change (coolant flow −2…−8 %) applied to both the params file and the world. T8 large (−15…−35 %). T9 undeclared degradation: world `R_ic_scale` 1.1–1.4 with **no file change**. T12 compound: 2–3 random changes from the applicable set (seeded).
- **Acceptance:** for T9, the scenario's change set is empty (assert it). For T7/T8, the params-file diff matches the world change.

## P5-07 — Evidence oracle (B0 rerun-all)
- **Owner:** sonnet · **Depends on:** P5-02
- **Files:** `bench/oracles/evidence.py`, `bench/tests/test_evidence_oracle.py`
- **Spec:** in the post-change workspace, run every producer for every claim's subject (cached by `(producer_id, code_hash, inputs hash, subject)`), assess, and return `{claim_id: (status, evidence values)}`. "Truly affected" label: status differs pre vs. post, **or** any relied-on evidence value moved > ε = 0.1 K.
- **Acceptance:** toy-project test with known labels.

## P5-08 — Truth oracles
- **Owner:** sonnet · **Depends on:** P5-05
- **Files:** `bench/oracles/truth.py`
- **Spec:** Tier A: the measured peak on recorded cycles (from data). Claims on synthetic cycles get `truth=None` and are excluded from UAR_truth in Tier A. Tier B: the world's noise-free peak. Returns `{claim_id: satisfied: bool | None}`.
- **Acceptance:** tests on fixtures. The None share is reported in the metrics output.

## P5-09 — Baselines B1–B4
- **Owner:** sonnet · **Depends on:** P5-07
- **Files:** `bench/baselines/{file_level,ood_only,naive,random_budget}.py`, `bench/tests/test_baselines.py`
- **Spec:** each baseline has `select_runs(pre_state, post_workspace) -> list[(producer_id, subject_id)]` and then executes through the same runner. B1 uses whole-file hashes (an independent tiny implementation, not `reval` field hashing). B2 keeps old evidence and reruns ML only where OOD under the new model. B3 runs nothing. B4 picks random runs up to ReVal's cost (seeded).
- **Acceptance:** on the toy project, B1 reruns strictly more than ReVal for a single-field change. B3 cost = 0.

## P5-10 — Metrics
- **Owner:** sonnet · **Depends on:** P5-07, P5-08, P5-09
- **Files:** `bench/analysis/metrics.py`, `bench/tests/test_metrics.py`
- **Spec:** implement exactly the `docs/06` §3 definitions: impact recall/precision, UAR_evidence, UAR_truth, decision coverage, cost ratio, false-alarm cost, reproducibility, optimality gap. Input: a tidy per-(scenario, method, claim) DataFrame. Output: per-scenario metrics.
- **Acceptance:** hand-computed fixtures (≥ 1 test per metric, including the zero-division conventions: undefined → NaN and excluded, documented).

## P5-11 — Runner, cache, smoke config
- **Owner:** sonnet · **Depends on:** P5-10
- **Files:** `bench/run.py`, `bench/configs/smoke.yaml`, `bench/configs/full.yaml`, `bench/cache.py`
- **Spec:** `python -m bench.run --config X [--jobs N]`. A joblib-parallel run over scenarios writes `bench/results/<config_hash>/rows.parquet`, `manifest.json` (git rev, config hash, package versions, seeds), and `rows.sha256`. A producer-result cache keyed by inputs hash.
- **Acceptance:** `python -m bench.run --config bench/configs/smoke.yaml` (≈ 2 scenarios per type) finishes in < 15 min on a laptop. Re-running hits the cache and gives identical `rows.sha256`.

## P5-12 — Statistics: cluster bootstrap + non-inferiority
- **Owner:** sonnet · **Depends on:** P5-10
- **Files:** `bench/analysis/stats.py`, `bench/tests/test_stats.py`
- **Spec:** `cluster_bootstrap(df, metric, by=["seed", "change_type"], n=10_000, seed=0) -> (estimate, lo, hi)`. Paired difference CIs between methods. `non_inferior(diff_hi, delta) -> bool`.
- **Acceptance:** test against a synthetic case with a known CI (normal data, analytic CI within tolerance). Determinism under a seed.

## P5-13 — Ablations A1–A7
- **Owner:** sonnet · **Depends on:** P5-11
- **Files:** `bench/configs/ablations/a1_no_field_selectors.yaml` … `a7_kappa.yaml`, plus ablation flags in `reval` **settings** (not code forks)
- **Spec:** add `ReValSettings` (pydantic) to services: `field_selectors: bool`, `carry_forward: bool`, `scope_freshness: bool`, `ad_mode: strict|relaxed|off`, `uncertainty: conformal|fixed_margin|cqr`, `planner: ilp|greedy`, `kappa: float`. The defaults are the main method. A1: treat all deps as `*`. A2: carry-forward off. A3: scope off. A4: AD modes. A5: fixed margin / CQR (implement `CQR` in `reval.uq`). A6: greedy. A7: κ ∈ {1.0, 1.5, 2.0, 3.0}.
- **Acceptance:** each ablation config runs in smoke mode. A unit test shows each flag changes behavior on a crafted toy case. **The core stays pure:** settings are passed in as arguments.
- **Pitfalls:** `ad_mode=off` must only be reachable through the bench settings. Document it in AGENTS.md as forbidden for real use.

## P5-14 — Cost sensitivity
- **Owner:** sonnet · **Depends on:** P5-11
- **Files:** `bench/configs/cost_sensitivity.yaml`
- **Spec:** bench cost ∈ {20, 100, 500}. Other costs fixed. Re-plan only (reuse cached evidence).
- **Acceptance:** results rows tagged with `cost_profile`.

## P5-15 — Figures and tables (scripted)
- **Owner:** sonnet · **Depends on:** P5-12, P5-13, P5-14
- **Files:** `bench/analysis/figures.py`, `bench/analysis/tables.py`, output → `bench/results/<hash>/figures/`
- **Spec:** (1) cost ratio vs. UAR per method, per change type; (2) impact recall/precision table per change type; (3) ablation table; (4) κ curve; (5) conformal coverage per length class (from P1); (6) optimizer O1/O2/O3 in-domain vs. truth (RQ4); (7) cost sensitivity. Tier A and Tier B are separate panels. Use the `dataviz` guidance: colorblind-safe, labeled units.
- **Acceptance:** `python -m bench.analysis.figures --results bench/results/<hash>` regenerates everything. No hand-edited numbers.

## P5-16 — Full run + archive (HUMAN REVIEW)
- **Owner:** sonnet+human-review · **Depends on:** P5-01, P5-15
- **Spec:** run `full.yaml` + ablations + cost sensitivity. Record result hashes in `docs/log/`. Write deviations from the pre-registration into `preregistration.md` §Deviations.
- **Acceptance:** the human reviews the headline numbers per change type before anything goes into the paper.
