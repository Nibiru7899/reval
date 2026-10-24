# 05 — Reference domain: PMSM thermal validation

## 1. Dataset

- **Source:** *Electric Motor Temperature*, Paderborn University, Dept. of Power Electronics and Electrical Drives (LEA).
  Kaggle: `wkirgsn/electric-motor-temperature`. 185 h of test-bench data at 2 Hz from a 52 kW three-phase automotive traction PMSM.
- **Expected columns** (assert in the loader; fail loudly on mismatch): `u_q, u_d, i_q, i_d, motor_speed, torque, coolant, ambient,
  stator_winding, stator_tooth, stator_yoke, pm, profile_id`.
- **Targets:** `pm` (rotor magnet, measured by telemetry; this is the hard and valuable one) and `stator_winding`. The other stator temperatures are secondary.
- **Session structure:** each `profile_id` is a separate measurement session of varying length. **Rows within a profile are strongly
  autocorrelated, so never split rows randomly.**
- **License:** check on the Kaggle page before redistributing anything. The repo never commits raw data. `scripts/download_data.py`
  fetches it (the Kaggle CLI needs the user's own API token, which the user sets up; ReVal never handles it).
- **Citation:** cite the dataset and the Kirchgässner et al. papers in every report and in the README.

## 2. Splits (fixed, committed as `examples/motor_thermal/splits.yaml`)

| Split | Use | Rule |
|---|---|---|
| `train` | Model fitting, LPTN identification | ~65 % of profiles |
| `calib` | Conformal calibration, AD thresholds | ~15 % of profiles, disjoint |
| `test` | RQ4 coverage, Tier A ground truth | ~20 % of profiles, disjoint. Use the published test profiles from Kirchgässner et al. where identifiable (check the paper's figure and the `wkirgsn` GitHub repo) so results are comparable. |
| `reserve` | Tier A "new data arrives" scenarios | A few train-like profiles withheld at first, appended during benchmark scenarios |

Stratify roughly by profile length and by operating-region coverage (coolant range, speed range). Record the split's hash.
**The splits file is itself an artifact** in the ReVal manifest, so changing a split is a tracked change.

## 3. Models (the "evidence producers" of kind `ml_prediction`)

| Id | Model | Features | Why |
|---|---|---|---|
| M1 | Ridge regression | Raw inputs + derived (`i_s = √(i_d²+i_q²)`, `u_s`, `P_el = i_s·u_s`, `i_s·ω`) + multi-span EWMAs (spans from minutes to ~1 h) | Strong, interpretable classical baseline in the literature. Fast. |
| M2 | `HistGradientBoostingRegressor` (point + quantile) | Same | Nonlinear. Quantile version enables CQR. |
| M3 | `MLPRegressor` (small) | Same | Shows the framework is model-agnostic |
| M4 (stretch) | Thermal Neural Network (PyTorch) | State-space | Only if time allows. Not needed for the research question. |

Report per-target MSE and max absolute error on `test` and compare against the published numbers for context (TNN ≈ 3.18 K²,
expert LPTN ≈ 3.64 K² MSE, averaged over targets). **Matching the literature isn't the goal.** A credible, honestly evaluated model is.

## 4. Independent physics model (producer of kind `physics_sim`)

A **4-node lumped-parameter thermal network** with nodes PM, stator yoke (SY), stator tooth (ST), and stator winding (SW).
Boundary conditions are coolant and ambient temperature.

```
C_i · dϑ_i/dt = P_i(i_s, u_s, ω, ϑ) + Σ_j (ϑ_j − ϑ_i) / R_ij + (ϑ_c − ϑ_i) / R_ic
```

- Losses: copper `P_cu ∝ i_s² · R_ref · (1 + α_cu (ϑ_SW − ϑ_ref))`, iron and magnet losses as low-order polynomials in ω and u_s.
- Identify (C, R, loss coefficients) on `train` with `scipy.optimize.least_squares`, using explicit-Euler simulation at Δt = 0.5 s
  (a vectorized NumPy loop; consider `numba` if it's too slow).
- Validate on `test` and compute the model-form band δ per target from the test residual distribution of peaks.
- If identification is unstable, the fallback is a 2-node network (PM, SW). Document the downgrade.
- **Independence caveat:** the LPTN is fitted on the same `train` data as the ML models. It is independent in *model form*,
  not in *data*. The report and the paper must say so. The `independent_of` policy constraint is about model form.

## 5. Drive map (from duty cycle to model inputs)

Duty cycles are defined in engineer terms (torque, speed, duration blocks). Models need `u_d, u_q, i_d, i_q`. Fit a regression from
(torque, speed, coolant) to (i_s, u_s, i_d, i_q, u_d, u_q) on steady segments of `train`. The drive map is **an artifact with its own
applicability domain**. A duty cycle that requires an unseen torque–speed combination is out of domain at the drive-map stage, and
the report says that is the reason.

## 6. Subjects and requirements

- **Duty cycles:** a library of about 40 parameterized cycles (`blocks` generator: 2–6 blocks of torque, speed, and duration, plus
  coolant and ambient), and about 40 *recorded* cycles (real `test`/`reserve` profile segments, for Tier A ground truth).
- **Declared limits** are set after EDA, at roughly the 90th–95th percentile of observed peak temperatures. That way a meaningful
  share of claims sits near the boundary, where validation matters. **These limits are study parameters, not the manufacturer's
  ratings.** Say so wherever they appear.
- **Non-thermal claims** (for locality tests): an analytic shaft-diameter tolerance claim and an inverter current-limit claim (max i_s
  over the cycle ≤ declared limit, computed through the drive map). The first must never be affected by thermal changes. The second
  shares the drive map, which tests partial overlap.

## 7. Producers and costs

| Producer | Kind | Fidelity | Cost (units) | Availability |
|---|---|---|---|---|
| `predict_peak_mX` | ml_prediction | 1 | 1 | Always |
| `lptn_sim` | physics_sim | 2 | 5 | Always |
| `bench_measure` | measurement | 3 | 100 | Tier A: only for recorded cycles (returns the real measured peak). Tier B: any cycle (queries the virtual world + sensor noise). |
| `shaft_check` | analytic | 3 | 1 | Always |
| `current_limit_check` | analytic | 2 | 1 | Always (through the drive map) |

Costs are relative: an order of magnitude between sim and bench is realistic. A cost-sensitivity analysis (bench at 20, 100, 500) is part of the evaluation.

## 8. The "virtual world" for Tier B

To get controllable ground truth for physical changes the dataset can't contain (a new coolant flow, a degraded thermal interface,
a sensor offset), Tier B uses a **world model**: an LPTN with a *different structure* from the design-time LPTN. It has more nodes,
temperature-dependent conductances, and is calibrated on *all* profiles. Physical changes are applied to the world model
(for example, scaling R_ic by 1.2). Bench measurements in Tier B query the world model with noise. The design-time models never see the world's parameters.

**Threat to validity:** when the world model and the design-time LPTN share structure, physics evidence looks better than it would on
real hardware. Mitigate with structural differences and an injected model-form error. Report Tier B results separately and label them as simulated.
