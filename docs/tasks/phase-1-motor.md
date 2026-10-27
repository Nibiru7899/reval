# Phase 1 — Motor reference domain (roadmap weeks 3–6)

All motor code lives in `examples/motor_thermal/motor/` and is importable as `motor`, because of the pytest `pythonpath`. Scripts live in
`examples/motor_thermal/scripts/` and are run as `.venv/Scripts/python examples/motor_thermal/scripts/<name>.py`. Each script resolves its paths
relative to `Path(__file__).parents[1]`, never the CWD.
**Binding names and signatures:** `docs/10-interfaces.md` §12 (motor) and §5 (`reval.uq`). They are quoted below. If anything here differs, §12/§5 win.
Unit tests go in `tests/unit/motor/` (no `__init__.py`) and `tests/unit/uq/`. They use **tiny synthetic frames** from
`tests.helpers.motor_synth.synthetic_measures(n_profiles=3, n_rows=600, seed=0)` (also exposed as the fixture factory `synthetic_measures` in `tests/unit/motor/conftest.py`), which has the real column names.
Tests that need the real data are marked `@pytest.mark.data`. Conventions: see the header of `phase-0-foundations.md`.

**Cross-phase dependencies (justified):** P1-01 needs `reval.errors.SchemaError`, and P1-06 needs `reval.domain.base.Frozen`. Both come from
P2-01, a small standalone task, so do P2-01 first.

---

## P1-01 — Download, validate, convert to parquet
- **Owner:** sonnet · **Depends on:** P0-01, P2-01 · **Read first:** `docs/05-motor-domain.md` §1, `docs/10` §12 (`data.py`), §13
- **Files:** `examples/motor_thermal/motor/__init__.py`, `examples/motor_thermal/motor/data.py`, `examples/motor_thermal/scripts/download_data.py`,
  `tests/__init__.py`, `tests/helpers/__init__.py`, `tests/helpers/motor_synth.py`, `tests/unit/motor/conftest.py`, `tests/unit/motor/test_data.py`
- **Spec (signatures from `docs/10` §12):**
  - `EXPECTED_COLUMNS: tuple[str, ...] = ("u_q", "coolant", "stator_winding", "u_d", "stator_tooth", "motor_speed", "i_d", "i_q", "pm", "stator_yoke", "ambient", "torque", "profile_id")`
  - `load_raw(path: Path) -> pd.DataFrame`: order-insensitive schema check. Raises `reval.errors.SchemaError` listing the missing and extra columns.
  - `validate(df: pd.DataFrame) -> None`: no NaNs, integer `profile_id`, ≥ 1 row per profile. Otherwise `SchemaError`.
  - `prepare(raw_csv: Path, out_parquet: Path) -> Path`: load → validate → add `t` (seconds, 0.5 s steps, restarting at 0 per profile) → sort by (profile_id, t) → write parquet → return `out_parquet`.
  - `scripts/download_data.py` (stdlib only, **no Kaggle CLI, no credentials**): if `data/raw/measures_v2.csv` exists, skip the download.
    Otherwise stream `https://www.kaggle.com/api/v1/datasets/download/wkirgsn/electric-motor-temperature` with `urllib.request` (it redirects to the archive) to `data/raw/archive.zip`,
    check the size is exactly `122_212_134` bytes (else delete it and exit 1 with a clear message), extract only `measures_v2.csv`
    with `zipfile`, then delete the zip. Require exactly one CSV in `data/raw/`. Then `prepare(...)` to `data/processed/measures.parquet`.
    The download URL and expected size are module constants (`DATASET_URL`, `ARCHIVE_BYTES`).
  - `tests/helpers/motor_synth.py::synthetic_measures(n_profiles=3, n_rows=600, seed=0) -> pd.DataFrame` (the conftest fixture returns this function) with exactly `EXPECTED_COLUMNS`. Temperatures are smooth
    first-order responses to the current, so the models in later tasks have something to learn.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_data.py` covers: a valid synthetic frame passes; a missing column → `SchemaError`;
  NaN → `SchemaError`; `t` restarts at 0 for each profile. A `@pytest.mark.data` test checks that the real parquet has 14 columns and > 1,000,000 rows.
- **Pitfalls:** don't add any authentication; the endpoint is public. Unit tests must not hit the network (test the extract/skip logic on a
  small zip made in `tmp_path`). The real file is already at `examples/motor_thermal/data/raw/measures_v2.csv` on the owner's machine.

## P1-02 — Profile-level splits
- **Owner:** sonnet+human-review · **Depends on:** P1-01 · **Read first:** `docs/05` §2, `docs/10` §12 (`splits.py`), AGENTS rule 6
- **Files:** `examples/motor_thermal/motor/splits.py`, `examples/motor_thermal/scripts/make_splits.py`, `examples/motor_thermal/splits.yaml` (generated, committed), `tests/unit/motor/test_splits.py`
- **Spec (from `docs/10` §12):**
  - `@dataclass(frozen=True) class Splits: train: tuple[int, ...]; calib: tuple[int, ...]; test: tuple[int, ...]; reserve: tuple[int, ...]` with `def of(self, profile_id: int) -> str`.
  - `make_splits(summary: pd.DataFrame, seed: int, test_ids: Sequence[int] | None, fractions: tuple[float, float, float] = (0.65, 0.15, 0.20), n_reserve: int = 3) -> Splits`.
    `test` = the published generalization profiles (`test_ids`, verified against the `upb-lea` code and noted in `source_note`), **plus** additional
    profiles drawn to reach ~20 % (R8). The remaining profiles are sorted by duration and dealt round-robin into train and calib, so each split spans
    short and long profiles. `reserve` is drawn from train-like profiles.
  - `save_splits(splits: Splits, path: Path, *, seed: int, source_note: str) -> None`. `load_splits(path: Path) -> Splits` asserts pairwise disjointness.
  - `split_frame(df: pd.DataFrame, splits: Splits, name: Literal["train", "calib", "test", "reserve"]) -> pd.DataFrame`.
  - `scripts/make_splits.py` writes `splits.yaml` (keys `train, calib, test, reserve, seed, source_note`), plus a `published_test_ids` key that lists the literature subset.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_splits.py`: the splits are disjoint and cover every profile; the same seed gives the same splits;
  `test_ids` ⊆ test; `split_frame` returns only the requested profiles. NEEDS HUMAN: review `splits.yaml` and `source_note`.
- **Pitfalls:** no row-level splitting anywhere. `reserve` profiles are **never** claim subjects (R5).

## P1-03 — Feature engineering (derived + EWMA)
- **Owner:** sonnet · **Depends on:** P1-01 · **Read first:** `docs/05` §3, `docs/10` §12 (`features.py`)
- **Files:** `examples/motor_thermal/motor/features.py`, `tests/unit/motor/test_features.py`
- **Spec (from `docs/10` §12):**
  - `INPUT_COLUMNS = ("u_q", "u_d", "i_q", "i_d", "motor_speed", "coolant", "ambient")`. Torque is **not** an input: it is itself an estimate.
  - `DERIVED = ("i_s", "u_s", "p_el", "i_s_x_w")`. `add_derived(df)`: `i_s = hypot(i_d, i_q)`, `u_s = hypot(u_d, u_q)`, `p_el = i_s * u_s`, `i_s_x_w = i_s * motor_speed`.
  - `EWMA_SPANS: tuple[int, ...] = (1320, 3360, 6360, 9480)`, in samples at 2 Hz. It's a parameter; record the final choice in the log.
  - `add_ewma(df, cols, spans)`: per profile (`groupby("profile_id")`), `ewm(span=s, adjust=False)`, which is causal and recursive. Column names are `"{col}_ewm{span}"`.
  - `make_features(df, spans=EWMA_SPANS) -> tuple[pd.DataFrame, list[str]]`: the frame and the ordered feature-name list (inputs, derived, then the EWMAs).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_features.py`: EWMA doesn't leak across profiles (the first row of profile 2 equals its raw value);
  the feature order is deterministic; a constant input gives a constant EWMA; with `adjust=False`, the EWMA equals the recursive formula on a 5-row example.

## P1-04 — Trajectory models M1–M3 + peak evaluation harness
- **Owner:** sonnet · **Depends on:** P1-02, P1-03 · **Read first:** `docs/05` §3, `docs/10` §12 (`models.py`)
- **Files:** `examples/motor_thermal/motor/models.py`, `examples/motor_thermal/scripts/train.py`, `tests/unit/motor/test_models.py`
- **Spec (from `docs/10` §12):**
  - `TARGETS = ("pm", "stator_winding")`. `class TrajectoryModel` with attributes `kind: Literal["ridge", "hgb", "mlp"]`, `feature_names: list[str]`, `targets: tuple[str, ...]`
    (constructor `TrajectoryModel(kind, targets=TARGETS, **hyperparams)`). Ridge is `StandardScaler + Ridge`. HGB and MLP come from sklearn with `random_state=0`.
    `fit(self, df_train) -> TrajectoryModel` and `predict(self, df) -> pd.DataFrame` (one column per target).
  - `peaks(y: pd.Series, profile_ids: pd.Series, window_rows: int) -> np.ndarray`: non-overlapping windows per profile. The trailing partial window is dropped.
  - `evaluate(model, df_test, window_rows) -> dict[str, Any]`: per-target MSE (K²), max abs error, and peak MAE.
  - `save(model: TrajectoryModel, path: Path, *, meta: Mapping[str, Any]) -> None` (joblib plus a sidecar `path.with_suffix(".json")` holding meta, the split hash, and metrics). `load(path: Path) -> TrajectoryModel`.
  - `scripts/train.py --model {ridge,hgb,mlp} --target {pm,stator_winding}` trains on `train` only and writes `models/tpm_<model>.joblib` (target pm) or
    `models/tsw_<model>.joblib` (target stator_winding). These artifact ids are used by the producers (`docs/10` §12).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_models.py`: ridge fits a linear synthetic target with MSE < 1e-3; `peaks` on a known ramp returns the window ends;
  a save/load round trip gives identical predictions. A `@pytest.mark.data` test checks that ridge's test MSE on `pm` is finite (no threshold).
- **Pitfalls:** fit the scaler on train only. `calib` and `test` never enter `fit`.

## P1-05 — Split-conformal (`reval.uq.conformal`) + motor `PeakConformal`
- **Owner:** sonnet · **Depends on:** P1-04 · **Read first:** `docs/04` A5, `docs/10` §5 and §12 (`conformal.py`)
- **Files:** `src/reval/uq/__init__.py`, `src/reval/uq/conformal.py`, `examples/motor_thermal/motor/conformal.py`, `tests/unit/uq/test_conformal.py`, `tests/unit/motor/test_motor_conformal.py`
- **Spec (binding API, `docs/10` §5):**
  - `conformal_quantile(scores: np.ndarray, alpha: float) -> float`: `n = len(scores)`, `k = ceil((n + 1) * (1 - alpha))`. Returns `inf` if `k > n`, else `sorted(scores)[k - 1]`.
    `ValueError` if alpha ∉ (0, 1) or the scores are empty.
  - `class SplitConformal`: `__init__(self, alpha: float)`; `fit(self, y_true, y_pred) -> SplitConformal` (scores = `|y_true - y_pred|`);
    `fit_scores(self, scores) -> SplitConformal`; `interval(self, y_pred: float) -> tuple[float, float] | None` (None when q is inf); properties `q`, `n`.
  - `empirical_coverage(y_true, lo, hi) -> float`.
  - Motor (`docs/10` §12): `LENGTH_CLASSES = {"short": 1200, "medium": 3600, "long": 7200}`; `class PeakConformal` with
    `fit(self, model, df_calib, alpha) -> PeakConformal` (one `SplitConformal` per (target, length class), scores from non-overlapping window peaks),
    `interval(self, target, pred_peak, length_class) -> tuple[float, float] | None`, and `coverage(self, model, df_test) -> dict[str, dict[str, float]]`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/uq/test_conformal.py tests/unit/motor/test_motor_conformal.py`: `conformal_quantile` with n=9, α=0.1 gives the
  9th smallest score; n=5, α=0.1 gives `inf`, and `interval` returns `None`. A `@pytest.mark.slow` Hypothesis property checks that empirical coverage on
  exchangeable synthetic data is ≥ 1−α−0.05 averaged over 200 seeds.
- **Pitfalls:** `reval.uq` must not import `motor`. Don't use `np.quantile` interpolation.

## P1-06 — Applicability domain (`reval.uq.domain`)
- **Owner:** sonnet · **Depends on:** P1-05, P2-01 · **Read first:** `docs/04` A4, `docs/10` §5 (`domain.py`)
- **Files:** `src/reval/uq/domain.py`, `tests/unit/uq/test_domain.py`
- **Spec (binding, `docs/10` §5):** `class DomainReport(Frozen)` with `inside`, `first_violation`, `violating_features`, `frac_outside`, `max_knn_distance`, `threshold`, `box`, and `to_dict()`.
  `class ApplicabilityDomain(feature_names, k=10, box_quantiles=(0.005, 0.995), dist_quantile=0.99, max_train_rows=200_000)`:
  - `fit(X_train, X_calib)`: standardize on train (zero-variance features use std = 1); deterministic subsample via `np.random.default_rng(0)` down to `max_train_rows`;
    a `scipy.spatial.cKDTree`; the box from train quantiles; τ from the calib mean kNN distance at `dist_quantile`.
  - `check(X, *, min_inside_frac=1.0) -> DomainReport`. Strict (1.0): inside iff every row passes. Relaxed: inside iff `(1 - frac_outside) >= min_inside_frac`.
  - `to_dict()` / `from_dict(d)` round-trip (no joblib).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/uq/test_domain.py`: training points are inside; a point at +10σ is outside with the right feature in
  `violating_features`; `first_violation` is correct; the `to_dict`/`from_dict` round trip gives identical reports; two fits on the same data are identical.

## P1-07 — 4-node LPTN simulator + cooling parameters
- **Owner:** sonnet · **Depends on:** P1-03 · **Read first:** `docs/05` §4, `docs/10` §12 (`lptn.py`)
- **Files:** `examples/motor_thermal/motor/lptn.py`, `examples/motor_thermal/params/lptn.yaml` (initial guess), `examples/motor_thermal/params/cooling.yaml`, `tests/unit/motor/test_lptn.py`
- **Spec (from `docs/10` §12):**
  - `NODES = ("pm", "stator_yoke", "stator_tooth", "stator_winding")`. `@dataclass(frozen=True) class LPTNParams: C: dict[str, float]; R: dict[tuple[str, str], float]; k_cu; alpha_cu; k_fe1; k_fe2; k_pm`.
    The R pairs are SW–ST, ST–SY, SY–coolant (nominal `R_ic`), PM–ST, PM–ambient, and SW–ambient.
  - `r_coolant(r_ic_nominal: float, flow_scale: float) -> float` returns `r_ic_nominal * flow_scale ** -0.8` (forced convection; cite the source in the docstring).
  - `losses(i_s, u_s, w, theta_sw, p) -> dict[str, np.ndarray]`: P_cu at SW = `k_cu·i_s²·(1 + alpha_cu·(theta_sw − 20))`; iron loss split between ST and SY,
    ∝ `k_fe1·w + k_fe2·w²·u_s`; PM loss ∝ `k_pm·w²`.
  - `simulate(inputs: pd.DataFrame, p: LPTNParams, theta0: Mapping[str, float] | None = None, dt: float = 0.5, *, flow_scale: float = 1.0) -> pd.DataFrame`: one profile, explicit Euler, columns = `NODES`.
    `theta0` defaults to the coolant temperature at t = 0 for every node. Raises `ValueError` if `dt > min(R·C)/2` (stability guard).
  - `load_params(path: Path) -> LPTNParams` / `dump_params(p: LPTNParams, path: Path) -> None`, with flat pointer-friendly keys (`/R/sw_st`, `/C/pm`, `/loss/k_cu`).
  - `params/cooling.yaml`: `flow_scale: 1.0` (dimensionless, nominal), plus a comment explaining that it's the only route by which coolant flow enters the models (D21).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_lptn.py`: zero losses with coolant == ambient == theta0 → constant temperatures; a step loss rises
  monotonically to a 1-node analytic steady state within 1 %; `flow_scale=0.5` raises the steady state relative to 1.0; the stability guard raises.
- **Pitfalls:** units are °C absolute for temperatures, W for losses, K/W for R, and J/K for C. Write them in the module docstring.

## P1-08 — LPTN identification + model-form band
- **Owner:** sonnet · **Depends on:** P1-07, P1-02 · **Read first:** `docs/05` §4, `docs/10` §12 (`identify`, `model_form_band`)
- **Files:** `examples/motor_thermal/motor/lptn.py` (add the functions), `examples/motor_thermal/scripts/calibrate_lptn.py`, `tests/unit/motor/test_lptn_identify.py`
- **Spec:** `identify(df_train, p0, bounds, max_profiles=None, seed=0) -> tuple[LPTNParams, dict[str, Any]]` with `scipy.optimize.least_squares` on log-parameters,
  residuals over all four nodes, and subsampling to 1 sample per 10 s. `model_form_band(p, df_test, window_rows) -> dict[str, float]` returns the 95th
  percentile of |peak_sim − peak_true| per node, in K. The script writes `params/lptn.yaml` and `models/lptn_report.json` (MSE per node, bands, and the input hashes).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_lptn_identify.py`: data simulated from known params plus noise → R and C identified within 10 %.
  A test marked `data` and `slow` runs end to end with finite MSE.
- **Fallback (decide by end of week 5):** if the 4-node fit is unstable, add a 2-node (pm, stator_winding) variant behind `n_nodes=2` and log the decision.

## P1-09 — Drive map
- **Owner:** sonnet · **Depends on:** P1-03, P1-06 · **Read first:** `docs/05` §5, `docs/10` §12 (`drive_map.py`)
- **Files:** `examples/motor_thermal/motor/drive_map.py`, `examples/motor_thermal/scripts/fit_drive_map.py`, `tests/unit/motor/test_drive_map.py`
- **Spec (from `docs/10` §12):** `class DriveMap`:
  - `fit(self, df_train) -> DriveMap` selects steady rows (|Δspeed| and |Δtorque| over 10 s below thresholds) and regresses (torque, motor_speed) → (i_d, i_q, u_d, u_q)
    with one `HistGradientBoostingRegressor(random_state=0)` per output. It keeps an `ApplicabilityDomain` over (torque, motor_speed).
  - `to_inputs(self, torque, speed, coolant, ambient) -> pd.DataFrame` returns `INPUT_COLUMNS` at 2 Hz. `domain_report(self, torque, speed) -> DomainReport`.
  - The script writes `models/drive_map.joblib`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_drive_map.py`: a synthetic known linear map is recovered (R² > 0.99); a point far outside the fitted torque–speed region is out of domain.

## P1-10 — Duty-cycle generator + subject library
- **Owner:** sonnet · **Depends on:** P1-02, P1-03 · **Read first:** `docs/05` §6, `docs/03` §8 (manifest), `docs/10` §12 (`cycles.py`)
- **Files:** `examples/motor_thermal/motor/cycles.py`, `examples/motor_thermal/scripts/make_subjects.py`, `examples/motor_thermal/subjects.yaml` (generated), `tests/unit/motor/test_cycles.py`
- **Spec (from `docs/10` §12):** `blocks(params: Mapping[str, Any]) -> pd.DataFrame` takes `{"blocks": [[torque_Nm, speed_rpm, duration_s], ...], "coolant", "ambient"}` and returns
  torque, motor_speed, coolant, ambient, and t at 2 Hz. `recorded(profile_id, start_s, duration_s, df) -> pd.DataFrame` takes a real segment, from **test profiles only**.
  `length_class(duration_s) -> Literal["short", "medium", "long"]`. `make_library(seed: int, splits: Splits) -> list[dict[str, Any]]` makes 40 parametric and 40 recorded subjects
  (recorded ones from `test` only, never `reserve`). The script writes them to `subjects.yaml` in the manifest `subjects:` format (`kind: duty_cycle`,
  `generator: "motor.cycles:blocks"` or `"motor.cycles:recorded"`, `params`).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_cycles.py`: total rows = Σ duration × 2; the library is deterministic; recorded slices come only from test profiles.

## P1-11 — Design optimizer O1/O2/O3
- **Owner:** sonnet · **Depends on:** P1-05, P1-06, P1-09, P1-10 · **Read first:** `docs/04` A8, `docs/10` §12 (`optimizer.py`)
- **Files:** `examples/motor_thermal/motor/optimizer.py`, `examples/motor_thermal/scripts/optimize.py`, `tests/unit/motor/test_optimizer.py`
- **Spec (from `docs/10` §12):** `@dataclass(frozen=True) class OptResult: theta; subject_params; pred_peak; upper; ad_report`.
  `optimize(variant, model, conformal, ad, drive_map, limits, bounds, seed=0) -> OptResult`. θ = 3 blocks × (torque, speed), with fixed durations
  (600, 900, 300 s) and fixed coolant and ambient. Objective: maximize Σ torque·ω·duration. Uses `scipy.optimize.differential_evolution(seed=seed, polish=False, maxiter=50)`
  with penalty constraints. The script prints a table of all three variants and writes their subject params.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_optimizer.py` with a stub model (peak = a·torque): each variant respects its constraint; the O3 optimum is inside the AD box; the same seed gives the same result.
- **Pitfalls:** this is example code. Keep it out of `src/reval`.

## P1-12 — M1 milestone reproduction script
- **Owner:** sonnet · **Depends on:** P0-03, P0-06, P1-01, P1-02, P1-03, P1-04, P1-05, P1-06, P1-07, P1-08, P1-09, P1-10, P1-11, P1-13 · **Read first:** `docs/07` M1 DoD
- **Files:** `examples/motor_thermal/scripts/reproduce_m1.py`
- **Spec:** one command runs prepare → splits check → train M1–M3 (both targets) → calibrate (P1-13) → LPTN identify → drive map → coverage tables
  (α 0.1 and 0.05) → optimizer table. It writes `models/m1_report.json` with every number plus the input hashes.
- **Acceptance:** `.venv/Scripts/python examples/motor_thermal/scripts/reproduce_m1.py` runs from a clean clone after P0-03 (a test marked `data` and `slow` runs it with `--quick`).
  The log entry in `docs/log/` points to the report path and its SHA-256. No numbers are typed by hand.

## P1-13 — Calibration script: uq artifacts per model
- **Owner:** sonnet · **Depends on:** P1-05, P1-06 · **Read first:** `docs/04` A4–A5, `docs/10` §5, §12
- **Files:** `examples/motor_thermal/scripts/calibrate.py`, `tests/unit/motor/test_calibrate_script.py`
- **Spec:** `calibrate.py --model-artifact tpm_ridge` loads `models/tpm_ridge.joblib`, fits `PeakConformal` on `calib` and an `ApplicabilityDomain` on
  (train, calib) features, and writes `models/uq_tpm_ridge.joblib` = `{"conformal": PeakConformal, "ad": ad.to_dict(), "meta": {alpha, split hash, model hash}}`.
  This is the **only** place conformal and AD artifacts are produced (P4-03 reads them; it does not recalibrate).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/motor/test_calibrate_script.py` runs the script's `main(argv)` on synthetic data in `tmp_path` and checks the output keys.
- **Pitfalls:** calibration uses `calib` profiles only. The AD box comes from `train`.
