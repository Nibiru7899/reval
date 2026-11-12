# Hand-computed expectations for the mini project (all producers run once, nothing changed)

Parameters: scale = 1.0, gain = 2.0, d_mm = 30.00. Data: 3 groups x 20 rows, `x = i/10`, `temp = 20 + 10x + (+0.5 if i odd else -0.5)`,
so the surrogate (slope 10, intercept 20) has max |residual| = 0.5 K and the maximum recorded temperature is 39.5 degC (i = 19).
Subjects: S1 load max = 2.0, S2 load max = 3.9. Limits: temp_peak <= 80 degC, shaft_d <= 30.05 mm.

| Producer @ subject | Point | Interval | Verdict |
|---|---|---|---|
| predict_temp @ S1 (in domain) | 20 + 10*1.0*2.0 = 40.0 | [39.5, 40.5] | PASS |
| predict_temp @ S2 (out of domain) | 20 + 10*1.0*3.9 = 59.0 | [58.5, 59.5] | INCONCLUSIVE (out of domain) |
| sim_temp @ S1 | 20 + 10*2.0*1.0*2.0 = 60.0 | [58.0, 62.0] | PASS |
| sim_temp @ S2 | 20 + 10*2.0*1.0*3.9 = 98.0 | [96.0, 100.0] | FAIL |
| measure_temp @ S1 (not available for S2) | 39.5 | [39.0, 40.0] | PASS |
| shaft_check @ D1 | 30.0 | [30.0, 30.0] | PASS (30.0 <= 30.05) |

`sim_temp` declares a tolerance on `params#/load/scale`: sensitivity = 10 * gain * max(load) (S1: 40 K per unit, S2: 78 K per unit),
valid range [0.5, 1.5], backed by `A-sim-sens`. `predict_temp` assumes `A-ambient`. Predictors are disjoint (`surrogate` vs `params`),
so the ML and physics items are independent.

## Expected statuses (default policies)

| Claim | Policy | Status | Why |
|---|---|---|---|
| C-S1-TEMP | medium | SUPPORTED, clause 0 | ML (in domain, PASS) + independent physics (PASS); measurement also passes (clause 1) |
| C-S2-TEMP | medium | VIOLATED | physics interval [96, 100] has lo > 80 (FAIL dominates); ML is out of domain; no measurement for S2 |
| C-S1-HI | high | SUPPORTED, clause 0 | measurement PASS (physics + independent ML in domain also passes, clause 1) |
| C-SHAFT | low | SUPPORTED, clause 3 | analytic exact 30.0 <= 30.05; the only item on D1 |

Without any evidence every claim is INCONCLUSIVE (`NO_EVIDENCE`).
