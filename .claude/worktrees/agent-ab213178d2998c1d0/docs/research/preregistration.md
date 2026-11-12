# Pre-registration (fill in after the week-21 pilot; commit at the end of week 21, before the week-22 final run)

- **Date committed:**
- **Git commit of ReVal under test:**
- **Benchmark config hash:**
- **Pilot seeds (development only; never reused):**
- **Final-run seeds (fresh):**

## Hypotheses (see `docs/06-evaluation.md` §1)
- **H1** (intersection–union; all parts must hold):
  1. The upper bound of the 95 % CI of the paired mean log(C_ReVal / C_B1) is < 0.
  2. **Primary:** the one-sided 97.5 % upper bound of UAR_truth(ReVal) − UAR_truth(B0) is < δ.
  3. The one-sided 97.5 % upper bound of UAR_evidence(ReVal) is < δ (UAR_evidence(B0) ≡ 0).
  4. Decision coverage(ReVal) ≥ decision coverage(B0) − 2 pp.
- **H2 (impact recall):** the one-sided 97.5 % lower bound (stratified cluster bootstrap) of impact recall is ≥ 0.98, tested separately on Tier A and on Tier B excluding T9 (T9 reported descriptively).
- **H3 (applicability gating):** in Tier B, on O1 optima, UAR_truth(ReVal-gated) < UAR_truth(point-acceptance). One-sided test: the 97.5 % upper bound of the paired difference (gated − point, paired by optimizer run) is < 0. This is the primary contrast of the 2 × 2 {O1, O3} × {point, gated} design with N ≥ 50 runs per cell.
- H2 and H3 use Holm correction at α = 0.05.

## Fixed analysis decisions
- δ (absolute, and as a relative margin vs. the pilot UAR_truth(B0)):
- ε per target (= 0.1 · median conformal half-width q̂):
- Scenario counts per change type; number of distinct base snapshots (≥ 30):
- Primary metric per RQ (see `docs/06-evaluation.md` §3). Ratio metrics are ratios of sums, pooled per resample.
- CI method: stratified cluster bootstrap (strata = change type, clusters = base snapshot), 10,000 resamples, percentile/BCa
- Predicted UAR_truth floor near the limit from marginal conformal coverage (≈ α):
- Exclusion rules (for example, scenarios where B0 itself fails to run):
- Declared limits, α, κ, AD thresholds, costs:

## Deviations (append after the run, with reasons)
