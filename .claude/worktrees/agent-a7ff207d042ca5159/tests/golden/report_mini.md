# Decision-validity report: mini

_ReVal reports the state of recorded evidence against declared requirements. It does not certify safety._

**3 of 4 claims are supported by recorded evidence; 1 claim needs attention.**

Supported: 3 · Waived: 0 · Stale: 0 · Inconclusive: 0 · Violated: 1

## Claims

| Claim | Status | Requirement | Reasons |
|---|---|---|---|
| C-S1-HI | ✔ SUPPORTED | R-TEMP-HI: temp_peak <= 80.00 degC (high) | policy_satisfied |
| C-S1-TEMP | ✔ SUPPORTED | R-TEMP: temp_peak <= 80.00 degC (medium) | policy_satisfied |
| C-S2-TEMP | ✖ VIOLATED | R-TEMP: temp_peak <= 80.00 degC (medium) | requirement_violated |
| C-SHAFT | ✔ SUPPORTED | R-SHAFT: shaft_d <= 30.05 mm (low) | policy_satisfied |

## Evidence

### C-S1-HI

| Evidence | Producer | Verdict | Freshness | Interval | Limit |
|---|---|---|---|---|---|
| `1de15eb7ceda` | mini.producers:predict_temp | PASS | fresh_exact | [39.50, 40.50] degC | <= 80.00 degC |
| `4992c356ce1e` | mini.producers:sim_temp | PASS | fresh_exact | [58.00, 62.00] degC | <= 80.00 degC |
| `fbb4fcdea172` | mini.producers:measure_temp | PASS | fresh_exact | [39.00, 40.00] degC | <= 80.00 degC |

### C-S1-TEMP

| Evidence | Producer | Verdict | Freshness | Interval | Limit |
|---|---|---|---|---|---|
| `1de15eb7ceda` | mini.producers:predict_temp | PASS | fresh_exact | [39.50, 40.50] degC | <= 80.00 degC |
| `4992c356ce1e` | mini.producers:sim_temp | PASS | fresh_exact | [58.00, 62.00] degC | <= 80.00 degC |
| `fbb4fcdea172` | mini.producers:measure_temp | PASS | fresh_exact | [39.00, 40.00] degC | <= 80.00 degC |

### C-S2-TEMP

| Evidence | Producer | Verdict | Freshness | Interval | Limit |
|---|---|---|---|---|---|
| `06542071ef29` | mini.producers:predict_temp | INCONCLUSIVE | fresh_exact | [58.50, 59.50] degC | <= 80.00 degC |
| `4eba64bc08d0` | mini.producers:sim_temp | FAIL | fresh_exact | [96.00, 100.00] degC | <= 80.00 degC |

### C-SHAFT

| Evidence | Producer | Verdict | Freshness | Interval | Limit |
|---|---|---|---|---|---|
| `b8c631de7a86` | mini.producers:shaft_check | PASS | fresh_exact | [30.00, 30.00] mm | <= 30.05 mm |

## Revalidation plan

No plan is stored for this snapshot. Run `reval plan` to create one.

## Hashes

- report_hash: `00daff293224d87296e4886207cdb8ae0fcd4f8085c35ee31ec48fa13c2748ec`
- report_id: `00daff293224d872`
- snapshot: `886d7c2f321ea7c02e08a8ffbafed406dcef755d8e5500f74f6c0da0b4449762`
- git_rev: `-`
- reval_version: 0.0.1
- created_at: 2026-01-01T00:00:00+00:00

_ReVal reports the state of recorded evidence against declared requirements. It does not certify safety._
