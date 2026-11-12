# 05 — Reference domain: PMSM thermal validation

## 1. Dataset

- **Source:** *Electric Motor Temperature*, Paderborn University, Dept. of Power Electronics and Electrical Drives (LEA).
  Kaggle: `wkirgsn/electric-motor-temperature`. 185 h of test-bench data at 2 Hz from a 52 kW three-phase automotive traction PMSM.
- **Version:** Kaggle dataset version 3 (updated 2021-04-26). The 2021 update added 17 profiles (138 h → 185 h) and de-anonymized the data.
  Measurement sessions are 1–6 h long.
- **Expected columns** (assert in the loader; fail loudly on mismatch): `u_q, u_d, i_q, i_d, motor_speed, torque, coolant, ambient,
  stator_winding, stator_tooth, stator_yoke, pm, profile_id`.
- **Verified on 2026-10-27** (downloaded copy): the archive is `archive.zip` (122,212,134 bytes) containing one file, `measures_v2.csv`
  (300,061,411 bytes). It has exactly the 13 columns above, 1,330,816 rows (184.8 h at 2 Hz), and **69 profiles** (ids 2–81, with gaps).
- **Access (no account or token):** the public endpoint `https://www.kaggle.com/api/v1/datasets/download/wkirgsn/electric-motor-temperature` redirects to the archive. `scripts/download_data.py` uses it.
- **`torque` and `motor_speed` are estimates** derived from set currents and voltages, not torque-sensor measurements. This matters for the
  drive map (§5) and for engineer-term duty cycles: a "torque" block is a torque *estimate* level.
- **Targets:** `pm` (rotor magnet, measured by telemetry; this is the hard and valuable one) and `stator_winding`. The other stator temperatures are secondary.
- **Session structure:** each `profile_id` is a separate measurement session of varying length. **Rows within a profile are strongly
  autocorrelated, so never split rows randomly.**
- **License:** CC BY-SA 4.0 (Kaggle metadata, v3). Any redistributed derivative (processed parquet, modified profiles from T3 scenarios,
  world-model parameters fitted to the data) must be CC BY-SA 4.0 and attributed. ReValBench therefore publishes **generators, not derived data**.
  The repo never commits raw data. `scripts/download_data.py` fetches it anonymously from the public URL above. No credentials are involved.
- **Citation:** the Kaggle page asks users to cite Kirchgässner, Wallscheid, Böcker, *Estimating Electric Motor Temperatures with Deep Residual
  Machine Learning*, IEEE Trans. Power Electronics, 2021 (verify volume and pages, believed 36(7)). Also cite the dataset and the other
  Kirchgässner et al. papers ([01](01-problem-and-prior-art.md) §2.7) in every report and in the README.

## 2. Splits (fixed, committed as `examples/motor_thermal/splits.yaml`)

| Split | Use | Rule |
|---|---|---|
| `train` | Model fitting, LPTN identification | ~65 % of profiles |
| `calib` | Conformal calibration, AD thresholds | ~15 % of profiles, disjoint |
| `test` | RQ4 coverage, Tier A ground truth | ~20 % of profiles, disjoint. It contains the **published generalization profiles** from the Kirchgässner et al. line of work (a single validation profile and 2–3 test profiles, reported in later work as val = 58, test = 65, 72; verify the IDs against the `upb-lea` / `wkirgsn` code), **plus** additional profiles to reach ~20 %. Literature-comparable metrics are reported on the published subset only. |
| `reserve` | Tier A "new data arrives" scenarios | A few train-like profiles withheld at first, appended during benchmark scenarios. **Never claim subjects.** |

Stratify roughly by profile length and by operating-region coverage (coolant range, speed range). Record the split's hash.
**The splits file is itself an artifact** in the ReVal manifest, so changing a split is a tracked change.

## 3. Models (the "evidence producers" of kind `ml_prediction`)

| Id | Model | Features | Why |
|---|---|---|---|
| M1 | Ridge regression | Raw inputs + derived (`i_s = √(i_d²+i_q²)`, `u_s`, `P_el = i_s·u_s`, `i_s·ω`) + multi-span EWMAs (spans from minutes to ~1 h) | Strong, interpretable classical baseline in the literature. Fast. |
| M2 | `HistGradientBoostingRegressor` (point + quantile) | Same | Nonlinear. Quantile version enables CQR. |
| M3 | `MLPRegressor` (small) | Same | Shows the framework is model-agnostic |
| M4 (stretch) | Thermal Neural Network (PyTorch) | State-space | Only if time allows. Not needed for the research question. |

Report per-target MSE and max absolute error on the published test subset and compare against the published numbers for context
(small TNN with 64 parameters ≈ 3.18 K², expert LPTN ≈ 3.64 K² MSE, averaged over targets; the same paper's largest HPO-optimal TNN
reaches ≈ 2.87 K² with 1,525 parameters). **Matching the literature isn't the goal.** A credible, honestly evaluated model is.

## 4. Independent physics model (producer of kind `physics_sim`)

A **4-node lumped-parameter thermal network** with nodes PM, stator yoke (SY), stator tooth (ST), and stator winding (SW).
Boundary conditions are coolant and ambient temperature.

```
C_i · dϑ_i/dt = P_i(i_s, u_s, ω, ϑ) + Σ_j (ϑ_j − ϑ_i) / R_ij + (ϑ_c − ϑ_i) / R_ic
```

- **Coolant flow.** The dataset contains no coolant-flow variable, so flow is a *declared design parameter*, not a measured input.
  It enters only through `params/cooling.yaml#/flow_scale` (1.0 = the test-bench condition the data was recorded at), mapped onto the
  coolant-side resistances as `R_ic = R_ic,0 · flow_scale^-0.8`. The exponent comes from turbulent forced convection (Dittus–Boelter, Nu ∝ Re^0.8);
  cite a heat-transfer textbook for it.
  - The design LPTN reads this artifact field.
  - ML producers declare `cooling#/flow_scale` as a dependency **without** a sensitivity. Any flow change therefore invalidates ML evidence (fail-closed), because the ML models never saw flow variation.
  - The Tier B world model applies the same physical change through its own, different flow–conductance relation (§8).

- Losses: copper `P_cu ∝ i_s² · R_ref · (1 + α_cu (ϑ_SW − ϑ_ref))`, iron loss `∝ k_fe1·ω + k_fe2·ω²·u_s`, magnet loss `∝ k_pm·ω²·i_s²` (eddy losses grow with stator-current harmonics as well as frequency).
- Identify (C, R, loss coefficients) on `train` with `scipy.optimize.least_squares`, using explicit-Euler simulation at Δt = 0.5 s
  (a vectorized NumPy loop; consider `numba` if it's too slow).
- Validate on `test` and compute the model-form band δ per target from the test residual distribution of peaks.
- If identification is unstable, the fallback is a 2-node network (PM, SW). Document the downgrade.
- **Independence:** two evidence items are independent iff they come from different producer kinds **and** their producers' `predictors`
  (the model artifacts that actually produce the quantity) are disjoint. `lptn_sim` has `predictors = (lptn,)`, while `predict_pm_peak_ridge` has
  `predictors = (tpm_ridge,)`. Both also depend on the shared `drive_map`, but the drive map is an input mapping, not a predictor, so
  it doesn't break independence. Same definition as `docs/03` §3 and `docs/10`.
- **Independence caveat:** the LPTN is fitted on the same `train` data as the ML models. It is independent in *model form*,
  not in *data*. The report and the paper must say so.
- **Shared model-form error:** tolerance sensitivities (`docs/04` A3) are also estimated on this design LPTN, so physics evidence and
  carry-forward bounds share one model-form error. That is why ablations A2/A7 are primary.

## 5. Drive map (from duty cycle to model inputs)

Duty cycles are defined in engineer terms (torque, speed, duration blocks). Models need `u_d, u_q, i_d, i_q`. Fit a regression from
(torque, motor_speed) to (i_d, i_q, u_d, u_q) on steady segments of `train` (`DriveMap` in `docs/10` §12). Coolant and ambient are passed
through unchanged, and `i_s`, `u_s` are derived features computed afterwards. The drive map is **an artifact with its own
applicability domain**. A duty cycle that requires an unseen torque–speed combination is out of domain at the drive-map stage, and
the report says that is the reason.

## 6. Subjects and requirements

- **Duty cycles:** a library of about 40 parameterized cycles (`blocks` generator: 2–6 blocks of torque, speed, and duration, plus
  coolant and ambient), and about 40 *recorded* cycles (real `test` profile segments only, for Tier A ground truth). With 2 thermal
  targets plus the non-thermal claims, that is ≈ 170 claims.
- **Declared limits** are set after EDA, at roughly the 90th–95th percentile of observed peak temperatures. That way a meaningful
  share of claims sits near the boundary, where validation matters. **These limits are study parameters, not the manufacturer's
  ratings.** Say so wherever they appear.
- **Non-thermal claims** (for locality tests): an analytic shaft-diameter tolerance claim and an inverter current-limit claim (max i_s
  over the cycle ≤ declared limit, computed through the drive map). The first must never be affected by thermal changes. The second
  shares the drive map, which tests partial overlap.

## 7. Producers and costs

| Producer | Kind | Fidelity | Cost (units) | Availability |
|---|---|---|---|---|
| `predict_pm_peak_<model>`, `predict_sw_peak_<model>` (model ∈ ridge, hgb, mlp) | ml_prediction | 1 | 1 | Always. Verdict is inconclusive when out of domain, or when the conformal interval is unbounded (below). |
| `lptn_sim` | physics_sim | 2 | 5 | Always |
| `bench_measure` | measurement | 3 | 100 | Tier A: only for recorded **test** cycles (returns the real measured peak). Tier B: any cycle (queries the virtual world + sensor noise, with common random numbers keyed by scenario, producer, and subject). |
| `shaft_check` | analytic | 3 | 1 | Always |
| `current_limit_check` | analytic | 3 | 1 | Always (through the drive map). Fidelity 3, so it satisfies the `[analytic{min_fidelity: 3}]` clause of the medium policy. |

Costs are relative: an order of magnitude between sim and bench is realistic. A cost-sensitivity analysis (bench at 20, 100, 500) is part of the evaluation.

**Conformal small-sample rule.** The `calib` split is about 10 profiles, so window counts per length class can be in the tens. If a class has
`n < ⌈1/α⌉ − 1` calibration scores, the split-conformal quantile is unbounded (`q̂ = ∞`). The ML producer then emits `interval=None`, and its
verdict is INCONCLUSIVE with reason `MARGIN_BELOW_UNCERTAINTY`. To avoid this, merge length classes, or use profile-level calibration
(one score per profile = max over windows). Coverage verified on recorded test profiles does **not** transfer to drive-map (synthetic)
subjects, which carry an extra drive-map error. Their coverage is only checkable in Tier B and is reported separately.

## 8. The "virtual world" for Tier B

To get controllable ground truth for physical changes the dataset can't contain (a new coolant flow, a degraded thermal interface,
a sensor offset), Tier B uses a **world model**: an LPTN with a *different structure* from the design-time LPTN. It has more nodes,
temperature-dependent conductances, its own flow–conductance relation, and is calibrated on **train + reserve only** (never `calib` or `test`).
Physical changes are applied to the world model (for example, scaling R_ic by 1.2). Bench measurements in Tier B query the world model
with noise. The design-time models never see the world's parameters.

**Tier B ML models are retrained on world-model trajectories** generated from the train-split input profiles. Model and truth then refer to
the same plant, and ML error in Tier B measures ReVal behavior, not the world-to-real gap. The world model's fit error on test profiles is
reported separately as model-form discrepancy.

**Threat to validity:** when the world model and the design-time LPTN share structure, physics evidence looks better than it would on
real hardware. Mitigate with structural differences and an injected model-form error. Report Tier B results separately and label them as simulated.
