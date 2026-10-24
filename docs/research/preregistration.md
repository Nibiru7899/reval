# Pre-registration (fill in and commit before the final benchmark run, roadmap week 19)

- **Date committed:**
- **Git commit of ReVal under test:**
- **Benchmark config hash:**

## Hypotheses
- H1: ReVal cost < B1 cost (paired, per scenario), and UAR_evidence(ReVal) − UAR_evidence(B0) < δ = 1 pp (non-inferiority, 95 % upper bound).
- H2: Impact recall ≥ 0.98 on Tier A.
- H3: On optimizer-generated subjects, UAR_truth(O3 + ReVal) < UAR_truth(O1 point prediction).

## Fixed analysis decisions
- Scenario counts per change type, seeds:
- Primary metric per RQ: (see `docs/06-evaluation.md` §3)
- CI method: cluster bootstrap over (seed, change type), 10,000 resamples
- Exclusion rules (for example, scenarios where B0 itself fails to run):
- Declared limits, α, κ, AD thresholds, costs:

## Deviations (append after the run, with reasons)
