# Phase 1 — Motor reference domain (roadmap weeks 3–6)

All code lives in `examples/motor_thermal/motor/` (importable as `motor` thanks to the pytest `pythonpath` from P0-01; scripts run as
`python -m motor.<module>` from `examples/motor_thermal/`). Unit tests go in `tests/unit/motor/` and use **tiny synthetic frames**
built by `tests/unit/motor/conftest.py::synthetic_measures(n_profiles=3, n_rows=600, seed=0)`, which has the real column names.
Tests that need the real data are marked `@pytest.mark.data`.
Conventions: see the header of `phase-0-foundations.md`.

---

## P1-01 — Download, validate, convert to parquet
- **Owner:** sonnet · **Depends on:** P0-01 · **Read first:** `docs/05-motor-domain.md` §1
- **Files:** `motor/__init__.py`, `motor/data.py`, `scripts/download_data.py`, `tests/unit/motor/conftest.py`, `tests/unit/motor/test_data.py`
- **Spec:**
  - `EXPECTED_COLUMNS: tuple[str, ...] = ("u_q","coolant","stator_winding","u_d","stator_tooth","motor_speed","i_d","i_q","pm","stator_yoke","ambient","torque","profile_id")`
  - `load_raw(path: Path) -> pd.DataFrame`: read CSV. Raise `SchemaError` listing the missing or extra columns (order-insensitive).
  - `validate(df) -> None`: no NaNs in expected columns. `profile_id` is integer. Every profile has ≥ 1 row. Raise `SchemaError` with details.
  - `prepare(raw_csv, out_parquet) -> Path`: load → validate → add `t` (row index within profile × 0.5 s) → sort by (profile_id, t) → write parquet.
  - `scripts/download_data.py`: if `data/raw/*.csv` exists, skip. Otherwise call `kaggle datasets download -d wkirgsn/electric-motor-temperature -p data/raw --unzip`
    via `subprocess.run([...], check=True)`. If the `kaggle` CLI is missing, print manual-download instructions and exit 1.
    Then run `prepare` to `data/processed/measures.parquet`.
- **Acceptance:** tests cover: valid synthetic frame passes; missing column → `SchemaError`; NaN → `SchemaError`; `t` restarts at 0 per profile.
  `@pytest.mark.data` test: the real parquet has 13 + 1 columns and > 1,000,000 rows.
- **Out of scope:** feature engineering. **Pitfalls:** never read or print the Kaggle token. If the shipped CSV name differs, glob `data/raw/*.csv` and require exactly one file.

## P1-02 — Profile-level splits
- **Owner:** sonnet+human-review · **Depends on:** P1-01 · **Read first:** `docs/05` §2
- **Files:** `motor/splits.py`, `examples/motor_thermal/splits.yaml` (generated, committed), `tests/unit/motor/test_splits.py`
- **Spec:**
  - `Splits` (frozen dataclass): `train, calib, test, reserve: tuple[int, ...]`. `.of(profile_id) -> str`.
  - `make_splits(summary: pd.DataFrame, seed: int, test_ids: Sequence[int] | None, fractions=(0.65, 0.15, 0.20), n_reserve=3) -> Splits`.
    If `test_ids` is given (published test profiles), use them as test. Then sort the remaining profiles by duration and deal them round-robin
    into strata so each split spans short and long profiles. Draw `reserve` from train-like profiles (median-ish coolant range).
  - `save_splits(splits, path)` / `load_splits(path)`: YAML with keys `train, calib, test, reserve, seed, source_note`.
  - `split_frame(df, splits, name) -> pd.DataFrame`.
- **Acceptance:** tests: the splits are pairwise disjoint and cover all profiles; determinism under the same seed; `test_ids` honored;
  `split_frame` returns only the requested profiles. A human reviews `splits.yaml` (the source of the test ids is noted in `source_note`).
- **Pitfalls:** no row-level splitting anywhere (AGENTS rule 6).

## P1-03 — Feature engineering (derived + EWMA)
- **Owner:** sonnet · **Depends on:** P1-01 · **Read first:** `docs/05` §3
- **Files:** `motor/features.py`, `tests/unit/motor/test_features.py`
- **Spec:**
  - `INPUT_COLUMNS = ("u_q","u_d","i_q","i_d","motor_speed","coolant","ambient")` (torque is **not** an input: it is itself an estimate).
  - `add_derived(df)`: `i_s = hypot(i_d, i_q)`, `u_s = hypot(u_d, u_q)`, `p_el = i_s * u_s`, `i_s_x_w = i_s * motor_speed`.
  - `EWMA_SPANS: tuple[int, ...] = (1320, 3360, 6360, 9480)` (samples. Make it a parameter. It's a starting point; record the final choice in the log).
  - `add_ewma(df, cols, spans) -> pd.DataFrame`: EWMA **per profile** (`groupby("profile_id")`, `adjust=True`), column names `{col}_ewm{span}`.
  - `make_features(df, spans=EWMA_SPANS) -> tuple[pd.DataFrame, list[str]]`: returns the frame and the ordered feature-name list.
- **Acceptance:** tests: EWMA does not leak across profiles (the first row of profile 2 equals its raw value); feature list order is deterministic;
  a constant input gives a constant EWMA.

## P1-04 — Trajectory models M1–M3 + peak evaluation harness
- **Owner:** sonnet · **Depends on:** P1-02, P1-03 · **Read first:** `docs/05` §3
- **Files:** `motor/models.py`, `scripts/train.py`, `tests/unit/motor/test_models.py`
- **Spec:**
  - `TARGETS = ("pm", "stator_winding")`.
  - `TrajectoryModel` (class): `fit(df_train)`, `predict(df) -> pd.DataFrame[target]`, attributes `kind: Literal["ridge","hgb","mlp"]`,
    `feature_names`, `scaler`. Ridge uses `StandardScaler + Ridge(alpha)`. HGB and MLP come from sklearn with fixed `random_state`.
  - `peaks(y: pd.Series, profile_ids, window_rows) -> np.ndarray`: per-profile non-overlapping windows. A trailing partial window is dropped.
  - `evaluate(model, df_test, window_rows) -> dict`: per-target MSE (K²), max abs error, and peak MAE per window length.
  - `save(model, path)` / `load(path)` via joblib, plus a sidecar `path.with_suffix(".json")` with training config, the split hash, and metrics.
  - `scripts/train.py --model ridge --out models/tpm_ridge.joblib` trains on `train` only.
- **Acceptance:** synthetic test: ridge fits a linear synthetic target to MSE < 1e-3; `peaks` on a known ramp returns the window ends;
  save/load round-trip gives identical predictions. `@pytest.mark.data`: ridge test MSE on `pm` is finite and logged (no threshold).
- **Pitfalls:** fit the scaler on train only. `calib`/`test` are never used in `fit`.

## P1-05 — Split-conformal peak intervals (`reval.uq.conformal`)
- **Owner:** sonnet · **Depends on:** P1-04 · **Read first:** `docs/04` A5, `docs/10-interfaces.md` (reval.uq section)
- **Files:** `src/reval/uq/__init__.py`, `src/reval/uq/conformal.py`, `motor/conformal.py`, `tests/unit/test_conformal.py`, `tests/unit/motor/test_motor_conformal.py`
- **Spec:**
  - `conformal_quantile(scores: np.ndarray, alpha: float) -> float`: k = ceil((n+1)(1−alpha)). Return `inf` if k > n. Otherwise the k-th smallest score.
  - `SplitConformal`: `fit(residuals_abs, alpha)`, `.q`, `interval(point) -> tuple[float, float]`.
  - `motor/conformal.py::PeakConformal`: `fit(model, df_calib, window_rows_by_class: dict[str,int], alpha)` keeps one quantile per length class
    (`short` 10 min, `medium` 30 min, `long` 60 min); `interval(pred_peak, length_class)`; `coverage(model, df_test, ...) -> dict[class, float]`.
  - `scripts/train.py` gains `--calibrate`: fits PeakConformal on `calib` and stores it in the model sidecar.
- **Acceptance:** `conformal_quantile` matches hand-computed values for n=9, alpha=0.1 → the 9th smallest score, and n=5, alpha=0.1 → inf.
  Hypothesis property: on exchangeable synthetic data, empirical coverage ≥ 1−alpha−0.05 over 200 seeds (mark `slow`).
- **Pitfalls:** `reval.uq` must not import `motor`. It's a generic library helper.

## P1-06 — Applicability domain (`reval.uq.domain`)
- **Owner:** sonnet · **Depends on:** P1-03 · **Read first:** `docs/04` A4
- **Files:** `src/reval/uq/domain.py`, `tests/unit/test_domain_ad.py`
- **Spec:**
  - `DomainReport` (frozen dataclass): `inside: bool`, `first_violation: int | None`, `violating_features: tuple[str, ...]`,
    `frac_outside: float`, `max_knn_distance: float`, `threshold: float`, `box: dict[str, tuple[float, float]]`. Method `to_dict()`.
  - `ApplicabilityDomain(feature_names, k=10, box_quantiles=(0.005, 0.995), dist_quantile=0.99)`:
    `fit(X_train, X_calib)` standardizes on train, builds a `scipy.spatial.cKDTree`, sets the box from train quantiles, and sets the threshold τ
    from the calib mean kNN distances; `check(X, strict=True) -> DomainReport`. Strict: inside iff every row passes. Relaxed: `frac_outside ≤ 0.01`.
- **Acceptance:** tests: training points are inside; a point at +10σ is outside with the correct violating feature name; the first violation index is correct; determinism.
- **Pitfalls:** sub-sample `X_train` deterministically (`rng = np.random.default_rng(0)`, max 200k rows) to keep the tree fast. Record that in the report.

## P1-07 — 4-node LPTN simulator
- **Owner:** sonnet · **Depends on:** P1-03 · **Read first:** `docs/05` §4
- **Files:** `motor/lptn.py`, `examples/motor_thermal/params/lptn.yaml` (initial guess), `tests/unit/motor/test_lptn.py`
- **Spec:**
  - Nodes `("pm","stator_yoke","stator_tooth","stator_winding")`. `LPTNParams` (frozen dataclass): `C: dict[node,float]`, `R: dict[tuple[node,node],float]`
    (symmetric pairs: SW–ST, ST–SY, SY–coolant, PM–ST, PM–ambient, SW–ambient), loss coefficients `k_cu, alpha_cu, k_fe1, k_fe2, k_pm`.
  - `losses(i_s, u_s, w, theta_sw, p) -> dict[node, np.ndarray]`: P_cu at SW = k_cu·i_s²·(1+alpha_cu(theta_sw−20)); iron loss split ST/SY ∝ k_fe1·w + k_fe2·w²·u_s; PM loss ∝ k_pm·w².
  - `simulate(inputs: pd.DataFrame (one profile), p, theta0: dict | None, dt=0.5) -> pd.DataFrame[nodes]`: explicit Euler, vectorized per step.
    `theta0` defaults to coolant at t=0 for all nodes.
  - `load_params(yaml)` / `dump_params(p, yaml)`. The YAML is flat with JSON-pointer-friendly keys (`/R/sw_st`, `/C/pm`, `/loss/k_cu`) so the `yaml-fields` hasher gets one field per parameter.
- **Acceptance:** tests: zero losses and coolant == ambient == theta0 → constant temperatures; a step loss rises monotonically to the analytic steady state
  of a 1-node reduction within 1 %; stability guard: raise `ValueError` if dt > min(R·C)/2.
- **Pitfalls:** units: °C absolute for temperatures, W for losses, K/W for R, J/K for C. Document them in the module docstring.

## P1-08 — LPTN identification + model-form band
- **Owner:** sonnet · **Depends on:** P1-07, P1-02 · **Read first:** `docs/05` §4
- **Files:** `motor/lptn.py` (add `identify`), `scripts/calibrate_lptn.py`, `tests/unit/motor/test_lptn_identify.py`
- **Spec:** `identify(df_train, p0, bounds, max_profiles=None, seed=0) -> tuple[LPTNParams, dict]`. Uses `scipy.optimize.least_squares` on log-parameters
  (keeps them positive), with residuals over all four nodes, subsampled to 1 sample per 10 s for speed. `model_form_band(p, df_test, window_rows) -> dict[node, float]`:
  the 95th percentile of |peak_sim − peak_true|. The script writes `params/lptn.yaml` and `models/lptn_report.json` (MSE per node, bands).
- **Acceptance:** synthetic test: data simulated from known params + noise → identified params within 10 % on R/C. `@pytest.mark.data` + `slow`: runs end to end, finite MSE.
- **Fallback (decide by end of week 5):** if the 4-node fit is unstable, implement a 2-node (pm, stator_winding) variant behind `n_nodes=2` and log the decision.

## P1-09 — Drive map
- **Owner:** sonnet · **Depends on:** P1-03 · **Read first:** `docs/05` §5
- **Files:** `motor/drive_map.py`, `tests/unit/motor/test_drive_map.py`
- **Spec:** `DriveMap.fit(df_train)`: select steady rows (|Δspeed| and |Δtorque| over 10 s below thresholds). Regress (torque, motor_speed) → (i_d, i_q, u_d, u_q) with
  `HistGradientBoostingRegressor` per output (`random_state=0`). Has its own `ApplicabilityDomain` over (torque, motor_speed).
  `to_inputs(torque: np.ndarray, speed: np.ndarray, coolant, ambient) -> pd.DataFrame` with the model INPUT_COLUMNS; `domain_report(torque, speed) -> DomainReport`.
- **Acceptance:** synthetic test with a known linear map recovers it (R² > 0.99). A point far outside the fitted torque–speed region is reported out of domain.

## P1-10 — Duty-cycle generator + subject library
- **Owner:** sonnet · **Depends on:** P1-09 · **Read first:** `docs/05` §6, `docs/03` §6 (subjects)
- **Files:** `motor/cycles.py`, `examples/motor_thermal/subjects.yaml` (generated), `tests/unit/motor/test_cycles.py`
- **Spec:** `blocks(params: dict) -> pd.DataFrame`. `params = {"blocks": [[torque_Nm, speed_rpm, duration_s], ...], "coolant": degC, "ambient": degC}`
  → a 2 Hz trajectory with columns torque, motor_speed, coolant, ambient, t. `recorded(profile_id, start_s, duration_s, df) -> pd.DataFrame` slices a real segment.
  `length_class(duration_s) -> "short"|"medium"|"long"`. `make_library(seed) -> list[dict]`: 40 parametric + 40 recorded subjects (recorded from test/reserve),
  written to `subjects.yaml` in manifest `subjects:` format.
- **Acceptance:** tests: total rows = Σduration × 2; deterministic library; recorded slices come only from test/reserve profiles.

## P1-11 — Design optimizer O1/O2/O3
- **Owner:** sonnet · **Depends on:** P1-05, P1-06, P1-09, P1-10 · **Read first:** `docs/04` A8
- **Files:** `motor/optimizer.py`, `scripts/optimize.py`, `tests/unit/motor/test_optimizer.py`
- **Spec:** decision vector θ = 3 blocks × (torque, speed) with fixed durations (600, 900, 300 s) and fixed coolant/ambient. Objective: maximize Σ torque·ω·duration.
  `optimize(variant: Literal["O1","O2","O3"], model, conformal, ad, drive_map, limits, bounds, seed=0) -> OptResult(theta, subject_params, pred_peak, upper, ad_report)`
  using `scipy.optimize.differential_evolution(seed=seed, polish=False, maxiter=50)` with penalty constraints. The script prints a table of all three variants and saves the subjects.
- **Acceptance:** test with a stub model (peak = a·torque) checks the constraint is respected for each variant and O3 ⊆ the AD box. Determinism under the seed.
- **Pitfalls:** this is example code, not ReVal core. Keep it out of `src/reval`.

## P1-12 — M1 milestone reproduction script
- **Owner:** sonnet · **Depends on:** P1-01…P1-11 · **Read first:** `docs/07` M1 DoD
- **Files:** `examples/motor_thermal/scripts/reproduce_m1.py`, `docs/log/` entry
- **Spec:** one command runs prepare → splits check → train M1–M3 → calibrate → LPTN identify → coverage tables (alpha 0.1, 0.05) → optimizer table,
  and writes `models/m1_report.json` with every number plus input hashes.
- **Acceptance:** runs from a clean clone after P0-03. The numbers are copied into the log **by the script output path only** (no hand-typed numbers).
