# Motor tutorial: a coolant-flow change

The reference project is the thermal validation of a permanent-magnet synchronous motor (PMSM), built on the Paderborn
*Electric Motor Temperature* dataset. This page tells one story on it: **the coolant flow drops, and ReVal says which thermal claims
must be proven again.**

!!! info "Where the numbers come from"
    Every number below is copied from a committed log or demo output, not typed from memory:
    `DEMO.md` is `examples/motor_thermal/DEMO.md` (written by `demo_change.sh`),
    the plan figures are from `docs/log/2026-10-28-m4.md` (written by `demo_full.sh`), model metrics from `docs/log/2026-10-28-m1.md`,
    the physics model from `docs/log/2026-10-28-lptn.md`, and the limits from `docs/log/2026-10-28-limits.md`.
    Reproducing them needs the dataset and trained models; see the project README. They are study results on one public dataset.

## The project in four lines

- **Subjects** are duty cycles (`DC-P01`, `DC-R01`, ...) and one design (`SHAFT-1`). **Claims** say, for example, that duty cycle DC-P01 keeps the
  permanent-magnet temperature `pm` under its limit (`C-P01-PM`) or the stator winding under its limit (`C-P01-SW`).
- **Declared limits** are study parameters, taken from the *train* split only (42 profiles, 192 non-overlapping 30-min windows):
  `pm` 90 degC, `stator_winding` 130 degC, stator current `i_s` 315 A, shaft diameter 30.05 mm. They are **not** manufacturer ratings
  (source: `docs/log/2026-10-28-limits.md`).
- **Producers**: ML surrogates (ridge, MLP, histogram gradient boosting) with conformal intervals and an applicability-domain check; a coarse 4-node
  lumped-parameter thermal network (LPTN) as *independent* physics evidence; analytic checks for current and shaft; measurements from recorded profiles.
- **Splits** are by `profile_id`, never by random rows. Calibration and test profiles are never used for fitting.

### What the models know

From `docs/log/2026-10-28-m1.md` (test profiles, 30-min windows):

| artifact | MSE (K^2) | peak MAE (K) |
|---|---|---|
| tpm_hgb | 11.77 | 2.82 |
| tpm_mlp | 20.24 | 2.99 |
| tpm_ridge | 54.02 | 3.88 |
| tsw_hgb | 19.26 | 3.95 |
| tsw_mlp | 15.96 | 3.09 |
| tsw_ridge | 35.93 | 5.27 |

Empirical peak coverage of the 95 % conformal intervals on test profiles ranges from 0.918 to 1.000 across model and cycle-length class
(37 to 243 windows per class; the guarantee is marginal and windows of one profile are not exchangeable). The 4-node LPTN has a mean test MSE of
23.7 K^2 (expert 34-parameter LPTNs in the literature reach 3.64), so it is deliberately a wide-band independent source: physics alone is often
`INCONCLUSIVE` near the limit, and ReVal is meant to surface exactly that (`docs/log/2026-10-28-lptn.md`).

## Step 1: baseline

```console
$ reval snapshot --write ; reval run --all   (baseline, flow_scale: 1.0)
ran 20 producer results
CLAIM     BEFORE        AFTER         CLAUSE
C-P01-IS  INCONCLUSIVE  SUPPORTED     2
C-P01-PM  INCONCLUSIVE  INCONCLUSIVE  -
C-P01-SW  INCONCLUSIVE  INCONCLUSIVE  -
C-R01-PM  INCONCLUSIVE  SUPPORTED     0
C-R01-SW  INCONCLUSIVE  SUPPORTED     1
C-SHAFT   INCONCLUSIVE  SUPPORTED     3
```

(The demo trims the claims to `DC-P01`, `DC-R01` and `SHAFT-1` in a throwaway copy so it runs in minutes.) Note that `C-P01-PM` and `C-P01-SW` are
`INCONCLUSIVE` even at baseline (the first run reports no satisfied clause for them). ReVal does not accept evidence that fails to meet a policy clause, and
`explain C-P01-PM` on a real project shows which clause is unmet and why.

## Step 2: a small change, flow_scale 1.00 to 0.95

`params/cooling.yaml` holds the coolant flow scale. Edit it, re-lock, commit, and diff:

```console
$ reval diff HEAD~1 HEAD
KIND           TARGET               DETAIL
FIELD_CHANGED  cooling#/flow_scale  1.0 -> 0.95; delta -0.05

CLAIM     BEFORE        AFTER         AFFECTED  REASONS
C-P01-IS  SUPPORTED     SUPPORTED     no        policy_satisfied
C-P01-PM  INCONCLUSIVE  INCONCLUSIVE  yes       policy_unmet
C-P01-SW  INCONCLUSIVE  INCONCLUSIVE  yes       policy_unmet
C-R01-PM  SUPPORTED     STALE         yes       evidence_invalidated
C-R01-SW  SUPPORTED     STALE         yes       evidence_invalidated
C-SHAFT   SUPPORTED     SUPPORTED     no        policy_satisfied
```

What happened to the evidence (`DEMO.md`):

- The **LPTN** evidence is *carried forward*: `lptn_sim` declares a sensitivity tolerance on `cooling#/flow_scale`, so its interval is widened by
  kappa x sensitivity x |delta|, about 1.6 K here, instead of being thrown away.
- **Bench measurements** are *invalidated*: a measurement taken at the old flow does not support a claim at the new flow.
- **ML evidence** is *invalidated* too. It depends on `flow_scale` without a declared tolerance, so it fails closed.

At the claim level, the recorded-cycle claims `C-R01-PM` and `C-R01-SW` go `STALE`: their policies need a fresh measurement, or physics **plus** independent
ML, and carried-forward physics alone is not enough. `C-P01-IS` (current) and `C-SHAFT` are unaffected. They do not depend on cooling, so ReVal leaves them
alone: this is the cost saving.

## Step 3: a large change, flow_scale 0.95 to 0.75

```console
$ reval diff HEAD~1 HEAD
KIND           TARGET               DETAIL
FIELD_CHANGED  cooling#/flow_scale  0.95 -> 0.75; delta -0.2

CLAIM     BEFORE        AFTER         AFFECTED  REASONS
C-P01-IS  SUPPORTED     SUPPORTED     no        policy_satisfied
C-P01-PM  INCONCLUSIVE  INCONCLUSIVE  yes       policy_unmet
C-P01-SW  INCONCLUSIVE  INCONCLUSIVE  yes       policy_unmet
C-R01-PM  STALE         STALE         yes       evidence_invalidated
C-R01-SW  STALE         STALE         yes       evidence_invalidated
C-SHAFT   SUPPORTED     SUPPORTED     no        policy_satisfied
```

The change now exceeds the tolerance's valid range, so the carried-forward evidence is invalidated as well. Tolerances are only honoured inside the
range they were derived for, and each is backed by an assumption: this is the fail-closed rule in action.

## Step 4: the minimum-cost plan

For the 0.95 change, the planner (`docs/log/2026-10-28-m4.md`) found:

- Plan `8720762bf20d`: planner ilp, objective min_cost, solver OPTIMAL, **total cost 102.0, 3 runs**, unrestorable 0, deferred 0.

| producer | subject | cost | discharges |
|---|---|---|---|
| predict_pm_peak_ridge | DC-P01 | 1.0 | C-P01-PM/1/1 |
| predict_sw_peak_ridge | DC-P01 | 1.0 | C-P01-SW/0/0 |
| bench_measure | DC-R01 | 100.0 | C-R01-PM/0/0, C-R01-SW/1/0 |

One bench measurement of cost 100 discharges a conjunct of **both** `C-R01-PM` and `C-R01-SW`. The planner minimizes *expected* cost,
cost / p(decisive). Earlier ML and physics results on `DC-R01` were inconclusive by a wide margin, so cheap reruns had a low chance of
deciding anything. The measurement has p = 1 and wins even at 100× the price. After `reval run --plan latest`, both `C-R01` claims go from
STALE to **SUPPORTED**.

!!! note "What the plan could not fix"
    `C-P01-PM` and `C-P01-SW` stay `INCONCLUSIVE`. `DC-P01` is a parametric cycle, so no bench measurement exists for it in Tier A. The ML
    reruns had p = 0.5 and came back inconclusive again. ReVal reports the state of the evidence and doesn't make a claim true because a plan
    ran. An earlier version of the planner assumed every run is decisive. It planned five cheap runs (cost 9) and restored nothing, which is why
    decisiveness-aware planning (task P4-17) exists.

## Reproduce it

The demo scripts run on a throwaway copy of the project in a temporary git repository; the real `params/` are never touched.

```bash
bash examples/motor_thermal/demo_change.sh   # steps 1 to 3 (PowerShell: demo_change.ps1)
bash examples/motor_thermal/demo_full.sh     # adds plan, run --plan latest, report --html, explain
```

They need the processed data and trained models (the dataset is public and needs no credentials; it is downloaded by
`examples/motor_thermal/scripts/download_data.py`). `reval diff` exits `1` or `2` by design here; the scripts do not treat that as failure.

!!! danger "Not a safety statement"
    Statuses mean *supported by recorded evidence against the declared requirement*, using limits chosen for a study. They say nothing about whether
    a real motor is safe, certified, or compliant with a standard.

## Next

[Add ReVal to your project](tutorial-new-project.md) uses a much smaller domain you can finish in an hour, and shows how to write the manifest and producers
that this project already has.
