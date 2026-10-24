# 01 — Problem statement and prior art

## 1. Problem, stated precisely

Given:

- a set of **artifacts** (datasets, trained models, parameter files, assumptions, requirements, code), each versioned;
- a set of **evidence items**, each produced by running a **producer** (test, simulation, measurement, ML evaluation) on specific artifact versions, under declared conditions, with a recorded result;
- a set of **claims**, each asserting that a subject (a design, or an operating duty cycle) satisfies a requirement, and each governed by an **evidence policy** that says which combinations of evidence are sufficient;
- a **change** from snapshot *S* to snapshot *S′*.

Determine:

1. which evidence items are no longer *fresh* in *S′* (change impact);
2. for each claim, its status in *S′*: **Supported / Stale / Inconclusive / Violated** (validity assessment);
3. a minimum-cost set of producer runs that would restore every restorable claim to a decided status (revalidation planning);

All of this must be **deterministic, explainable, and reproducible**.

### Why the obvious approaches fail

| Approach | Failure mode |
|---|---|
| Re-run everything | Correct, but cost scales with project size. Bench time and high-fidelity simulation are expensive. |
| File-level dependency tracking (Make/DVC style) | Over-invalidates. Editing the coolant parameter in `params.yaml` invalidates every claim that reads `params.yaml`, even claims that don't use coolant. It is also blind to semantic scope: appending new data far from a claim's operating region still triggers it. |
| Out-of-distribution check only | Misses non-input changes such as a tightened requirement, a changed assumption, or a recalibrated sensor. It says nothing about *which tests* to run. |
| Trust the optimizer's constraint check | Optimizers seek out regions where the surrogate model is wrong. A "feasible" optimum is often an extrapolation. |
| Engineer judgment | Doesn't scale, isn't recorded, and is the failure mode V&V standards exist to remove. |

## 2. Prior-art map

ReVal builds on six existing lines of work. Its proposed contribution is the **combination**, applied at the level of
individual engineering decisions and evaluated on a benchmark. No single component below is claimed as new.

> **Citation hygiene:** every reference must be checked against the primary source before it appears in a report or
> paper. References marked ✅ are well-established and were known to the plan author. References marked ⚠️ came from
> the original Codex text and could **not** be verified while writing this plan. Find the primary source or drop them.

### 2.1 Truth maintenance and belief revision ✅
- Doyle, J. (1979). *A truth maintenance system.* Artificial Intelligence 12(3).
- de Kleer, J. (1986). *An assumption-based TMS.* Artificial Intelligence 28(2).
- **Relevance:** ReVal's claim–evidence–assumption graph is a justification network. Retracting an assumption propagates
  "out" labels — the same operation as invalidating evidence. ReVal adds continuous quantities, tolerance-based
  non-propagation, and cost-aware restoration.

### 2.2 Build systems and incremental computation ✅
- Mokhov, Mitchell, Peyton Jones (2018). *Build systems à la carte.* ICFP. (Verifying traces, constructive traces, early cutoff.)
- Bazel, Nix, DVC: content-addressed, hash-based rebuild decisions.
- **Relevance:** evidence freshness works like a verifying trace. *Tolerance-aware invalidation* generalizes early cutoff
  from "output hash unchanged" to "change provably below the sensitivity bound within the declared scope".

### 2.3 Regression test selection (software engineering) ✅
- Gligoric, Eloussi, Marinov (2015). *Practical regression test selection with dynamic file dependencies* (Ekstazi). ISSTA.
- Legunsen et al. (2016). *An extensive study of static regression test selection in modern software evolution.* FSE.
- Yoo & Harman (2012). *Regression testing minimization, selection and prioritization: a survey.* STVR.
- **Relevance:** "safe" RTS (never skip a test whose outcome could change) is exactly ReVal's safety requirement.
  Test-suite *minimization* is a set-cover problem. Engineering evidence differs because outcomes are continuous and
  uncertain, and tests vary in cost by orders of magnitude.

### 2.4 Model credibility and V&V standards ✅
- ASME V&V 40-2018: *Assessing credibility of computational modeling through verification and validation* (risk-informed credibility: model influence × decision consequence).
- NASA-STD-7009 (Standard for Models and Simulations) and its credibility assessment scale.
- Oberkampf & Roy (2010). *Verification and Validation in Scientific Computing.* Cambridge UP.
- Sandia PCMM (Predictive Capability Maturity Model).
- National Academies (2023/2024). *Foundational Research Gaps and Future Directions for Digital Twins* (stresses VVUQ).
- **Relevance:** these define *what* credible evidence is. ReVal's evidence policies encode V&V-40-style risk tiers in
  machine-checkable form. ReVal does **not** implement any standard, and the report must say so.

### 2.5 Assurance cases ✅
- Kelly, T. (1998). *Arguing safety* (PhD thesis, York). Goal Structuring Notation (GSN).
- Denney & Pai, AdvoCATE and work on dynamic / automated assurance cases (NASA Ames).
- Work on assurance-case change impact analysis (safety case maintenance).
- **Relevance:** this is the closest conceptual neighbor. A ReVal claim with its evidence policy is a small, quantitative
  assurance argument. The prior-art review must check carefully how far *dynamic assurance cases* already go toward
  automatic re-evaluation and cost-optimal restoration.

### 2.6 Uncertainty quantification and applicability domain ✅
- Angelopoulos & Bates (2021). *A gentle introduction to conformal prediction and distribution-free UQ.*
- Romano, Patterson, Candès (2019). *Conformalized quantile regression.* NeurIPS.
- Tibshirani, Barber, Candès, Ramdas (2019). *Conformal prediction under covariate shift.* NeurIPS.
- Applicability-domain methods from QSAR (OECD validation principles): range box, distance-to-training, density.
- **Relevance:** conformal intervals are only valid under exchangeability. That breaks exactly when the optimizer pushes
  outside the data, which is why ReVal gates conformal bounds behind an applicability-domain check.

### 2.7 Domain-specific: PMSM thermal modeling ✅
- Kirchgässner, Wallscheid, Böcker. *Data-driven permanent magnet temperature estimation in synchronous motors with supervised machine learning* (IEEE, ~2021) and related work.
- Kirchgässner, Wallscheid, Böcker (2023). *Thermal neural networks: Lumped-parameter thermal modeling with state-space machine learning.* Engineering Applications of AI 117. arXiv:2103.16323. (Reports TNN MSE 3.18 K² with 64 parameters, against an expert LPTN at 3.64 K² with 34 parameters.)
- Wallscheid & Böcker (2016). *Global identification of a low-order lumped-parameter thermal network for permanent magnet synchronous motors.* IEEE Trans. Energy Conversion.
- Dataset: *Electric Motor Temperature*, Paderborn University LEA, Kaggle `wkirgsn/electric-motor-temperature`. 185 h at 2 Hz from a 52 kW automotive traction PMSM.

### 2.8 Commercial / adjacent tools
- SmartUQ (UQ, calibration, DOE). Ansys Minerva and Siemens Teamcenter Simulation (SPDM, traceability).
  Requirements tools (IBM DOORS, Polarion, Jama). MBSE (Capella, SysML v2).
- MLflow, DVC, W3C PROV (provenance).
- **Positioning:** these are large, proprietary, or provenance-only. None of them, as far as this plan's author knows, combines
  *decision-level* freshness, applicability gating, and cost-optimal revalidation in an open, benchmarked workflow.
  **This must be verified in the formal prior-art review (Phase 0).**

### 2.9 Items from the original concept that need verification ⚠️
- "December 2025 survey of 50 industry and academic participants on simulation credibility" (Springer). Find the paper or drop it.
- "UK government's 2025 digital-twin definition requiring validation envelopes and assumption sets". Find the primary document.
- "OpenModelica traceability research, 2021 (MDPI)". Likely real (Linköping / OpenModelica traceability work). Get the exact citation.
- "Reliability-based model-validation research, 2026 (ScienceDirect)". Find it or drop it.
- "Simulator-backed engineering agents, August 2026 (arXiv)". Find it or drop it.

## 3. Claimed contribution (to be defended, not assumed)

1. **A formal model** of decision-level evidence freshness with four-valued claim status and *tolerance-aware invalidation*, with stated soundness conditions.
2. **A revalidation planner** that formulates evidence restoration as an ILP over evidence-policy alternatives, with shared tests and a budgeted variant.
3. **ReValBench**, a public benchmark of controlled engineering changes with ground truth on a real motor dataset, including baselines.
4. **An open-source implementation** (library, CLI, UI, CI action) and an empirical study answering RQ1–RQ5.

## 4. Prior-art review protocol (Phase 0, week 1–2)

- Search Google Scholar, IEEE Xplore, ACM DL, arXiv, and Scopus with these strings:
  `"change impact analysis" AND (simulation OR "digital twin") AND validation`,
  `"dynamic assurance case"`, `"assurance case" AND "change impact"`,
  `"regression test selection" AND (simulation OR "cyber-physical")`,
  `"model credibility" AND automat*`, `"applicability domain" AND surrogate AND optimization`,
  `"truth maintenance" AND engineering design`, `"validation envelope" OR "validity domain" AND model`.
- Snowball backward and forward from: ASME V&V 40, Denney & Pai, Mokhov 2018, Gligoric 2015.
- For each hit, fill one row in `docs/research/related-work.csv`: citation, what it does, overlap with ReVal (none / partial / full), data used, is code available.
- **Kill criterion:** if a published open tool already does decision-level freshness + applicability gating + cost-optimal
  restoration *with a benchmark*, pivot the contribution. Candidates: tolerance-aware invalidation alone, or the benchmark alone.
  Discuss this with your supervisor before week 3.
