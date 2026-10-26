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
> paper. References marked ✅ are well-established; their bibliographic details were spot-checked in the 2026-10-26 plan audit
> (`docs/log/2026-10-26-audit-decisions.md`). Items from the original Codex text were resolved in §2.9.

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
- Yoo & Harman (2012). *Regression testing minimization, selection and prioritization: a survey.* STVR 22(2).
- **Relevance:** "safe" RTS (never skip a test whose outcome could change) is exactly ReVal's safety requirement.
  Test-suite *minimization* is a set-cover problem. Engineering evidence differs because outcomes are continuous and
  uncertain, and tests vary in cost by orders of magnitude.

### 2.4 Model credibility and V&V standards ✅
- ASME V&V 40-2018: *Assessing Credibility of Computational Modeling through Verification and Validation: Application to Medical Devices* (risk-informed credibility: model influence × decision consequence). Its scope is medical devices. ReVal borrows only the risk-informed framework.
- NASA-STD-7009 (Standard for Models and Simulations) and its credibility assessment scale.
- Oberkampf & Roy (2010). *Verification and Validation in Scientific Computing.* Cambridge UP.
- Oberkampf, Pilch, Trucano (2007). *Predictive Capability Maturity Model for Computational Modeling and Simulation.* Sandia report SAND2007-5948 (PCMM).
- National Academies of Sciences, Engineering, and Medicine (2024). *Foundational Research Gaps and Future Directions for Digital Twins.* doi:10.17226/26894 (stresses VVUQ).
- **Relevance:** these define *what* credible evidence is. ReVal's evidence policies encode V&V-40-style risk tiers in
  machine-checkable form. ReVal does **not** implement any standard, and the report must say so.

### 2.5 Assurance cases ✅
- Kelly, T. (1998). *Arguing safety* (PhD thesis, York). Goal Structuring Notation (GSN).
- Denney & Pai, AdvoCATE and work on dynamic / automated assurance cases (NASA Ames).
- Denney, Pai, Habli (2015). *Dynamic safety cases for through-life safety assurance.* ICSE (NIER track). (Details from memory; verify.)
- Work on assurance-case change impact analysis (safety case maintenance).
- **Relevance:** this is the closest conceptual neighbor. A ReVal claim with its evidence policy is a small, quantitative
  assurance argument. The prior-art review must check carefully how far *dynamic assurance cases* already go toward
  automatic re-evaluation and cost-optimal restoration.

### 2.6 Uncertainty quantification and applicability domain ✅
- Angelopoulos & Bates (2021). *A gentle introduction to conformal prediction and distribution-free UQ.* arXiv:2107.07511 (later in Foundations and Trends in ML, 2023).
- Romano, Patterson, Candès (2019). *Conformalized quantile regression.* NeurIPS.
- Tibshirani, Barber, Candès, Ramdas (2019). *Conformal prediction under covariate shift.* NeurIPS.
- Applicability-domain methods from QSAR (OECD validation principles): range box, distance-to-training, density.
- **Relevance:** conformal intervals are only valid under exchangeability. That breaks exactly when the optimizer pushes
  outside the data, which is why ReVal gates conformal bounds behind an applicability-domain check.

### 2.7 Domain-specific: PMSM thermal modeling ✅
- Kirchgässner, Wallscheid, Böcker (2021). *Data-Driven Permanent Magnet Temperature Estimation in Synchronous Motors with Supervised Machine Learning: A Benchmark.* IEEE Trans. Energy Conversion 36(3):2059–2067. doi:10.1109/TEC.2021.3052546. arXiv:2001.06246.
- Kirchgässner, Wallscheid, Böcker (2021). *Estimating Electric Motor Temperatures with Deep Residual Machine Learning.* IEEE Trans. Power Electronics (believed 36(7); verify volume/pages). **This is the citation the Kaggle dataset page requests.**
- Kirchgässner, Wallscheid, Böcker (2023). *Thermal neural networks: Lumped-parameter thermal modeling with state-space machine learning.* Engineering Applications of AI 117, article 105537. arXiv:2103.16323. (Reports a small TNN at MSE 3.18 K² with 64 parameters, against an expert LPTN at 3.64 K² with 34 parameters. Its largest HPO-optimal TNN reaches 2.87 K² with 1,525 parameters.)
- Wallscheid & Böcker (2016, online 2015). *Global identification of a low-order lumped-parameter thermal network for permanent magnet synchronous motors.* IEEE Trans. Energy Conversion 31(1):354–365.
- Dataset: *Electric Motor Temperature*, Paderborn University LEA, Kaggle `wkirgsn/electric-motor-temperature` (v3, 2021-04-26, CC BY-SA 4.0). 185 h at 2 Hz from a 52 kW (22 kW nominal) automotive traction PMSM. `torque` is estimated from currents/voltages, not measured.

### 2.8 Commercial / adjacent tools
- SmartUQ (UQ, calibration, DOE). Ansys Minerva and Siemens Teamcenter Simulation (SPDM, traceability).
- Requirements tools (IBM DOORS, Polarion, Jama). MBSE (Capella, SysML v2).
- OpenModelica traceability: *an integrated traceability system inside OpenModelica*, MDPI Electronics 10(8):983 (2021). Graph-based traceability and change-impact analysis across requirements and simulations. Authors not yet retrieved (likely Mengist, Pop et al., Linköping); confirm.
- GOV.UK (Dstl / National Digital Twin Programme), *Digital twin definition*, published 29 Oct 2025. Cite only for what the text actually says.
- MLflow, DVC, W3C PROV (provenance).
- **Positioning:** these are large, proprietary, or provenance-only. None of them, as far as this plan's author knows, combines
  *decision-level* freshness, applicability gating, and cost-optimal revalidation in an open, benchmarked workflow.
  **This must be verified in the formal prior-art review (Phase 0).**

### 2.9 Items from the original concept (resolved in the 2026-10-26 audit)

| Original claim | Outcome | Action |
|---|---|---|
| OpenModelica traceability research, 2021 (MDPI) | **Found:** MDPI Electronics 10(8):983, April 2021 | Cited in §2.8. Confirm the author list. |
| UK government's 2025 digital-twin definition "requiring validation envelopes and assumption sets" | **Partially found:** GOV.UK *Digital twin definition* (Dstl / NDTP), 29 Oct 2025. Nothing found supports the "validation envelopes and assumption sets" wording. | Cite the definition only for what it says. Drop the envelope claim unless it is in the text. |
| December 2025 Springer survey of 50 participants on simulation credibility | **Not found** | Dropped |
| Reliability-based model-validation research, 2026 (ScienceDirect) | **Not found** | Dropped |
| Simulator-backed engineering agents, August 2026 (arXiv) | **Not found.** The only Aug 2026 hit (arXiv:2608.24650) is about LLM-serving simulators, which isn't relevant. | Dropped |

## 3. Claimed contribution (to be defended, not assumed)

1. **A formal model** of decision-level evidence freshness with five-valued claim status (four in benchmarks, which contain no waivers) and *tolerance-aware invalidation*, with stated soundness conditions.
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
