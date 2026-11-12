# Prior-art summary (P0-04)

> **DRAFT for the owner to verify.** Written by an AI assistant from web-search results and abstract pages only. No primary source was read in full, and every row in `related-work.csv` has `verified=no`. Treat every claim below as a lead, not a finding. Searches were run in October 2026 and cover the strings in `docs/01` section 4 only in part (see "Gaps").

## The three closest works

1. **MMINT-A (Fung et al., 2018) and ExplicitCase (fortiss), with the Cârlan et al. (2021) review.** These tools compute which assurance-case (GSN) elements a model change affects. The 2021 systematic review reports that such approaches over-flag affected elements and rarely quantify impact. That is the gap ReVal targets. *Difference:* ReVal works on quantitative claims with tolerances, so a change below a declared sensitivity bound need not invalidate. It also plans the cheapest restoring tests, which these tools were not described as doing.
2. **Abeywickrama et al., "Towards continuous assurance with formal verification and assurance cases" (arXiv 2025).** Regenerates assurance arguments when specifications or verification results change. *Difference:* it targets formal verification, shows one robot case study, and the abstract mentions no benchmark, applicability gating, or cost-optimal planning.
3. **Mertens and Denil, "Reusing model validation methods for the continuous validation of digital twins of CPS" (2025).** Continuously checks whether a simulation-based twin still matches its physical system, and re-estimates parameters. *Difference:* it validates a model against data, not decision-level claims with evidence policies. It has no freshness bookkeeping, no restoration planning, and no benchmark (none stated on the arXiv page).

Also relevant: Denney, Pai and Habli (2015) and Denney and Pai (2024) on dynamic safety cases, and Van Mierlo et al. (2020) on validity frames, which is the nearest idea to an applicability gate.

## Six lineages

| Lineage | Representative works (see CSV) | What it gives ReVal | What it lacks for ReVal |
|---|---|---|---|
| Truth maintenance (TMS) | Doyle 1979; de Kleer 1986 | Justification graph, retraction propagation | Discrete beliefs only; no tolerances, no cost |
| Build systems / incremental computation | Mokhov et al. 2018; Adapton 2014; PROV-O | Verifying traces, early cutoff, provenance | Hash equality only; no semantic scope, no status |
| Regression test selection | Ekstazi 2015; Legunsen 2016; Yoo and Harman 2012; Simulink prioritization (2025) | Safe selection; test minimization as set cover | Boolean pass/fail tests, code dependencies, unit costs |
| V&V and model credibility | ASME V&V 40; NASA-STD-7009; PCMM; Oberkampf and Roy; NASEM 2024; Mertens and Denil 2025 | Risk-tiered credibility, "what is enough evidence" | Manual, document-based; NASEM names automated online VVUQ as an open gap |
| Assurance cases (incl. dynamic) | MMINT-A; ExplicitCase; Jaradat et al.; Cheng et al. 2022; Denney et al.; Abeywickrama et al. 2025; Cârlan et al. 2021 | Closest conceptual neighbour: claim, argument, evidence, change impact | Qualitative, over-approximate impact; no cost-optimal restoration seen; no public benchmark seen |
| UQ and applicability domain | Conformal prediction (3 works); OECD QSAR guidance; Schweidtmann et al. 2022; validity frames | Calibrated intervals; domain-of-validity checks | Intervals break outside the data; not tied to claim status or test planning |

## Kill criterion assessment (DRAFT: owner must verify before the scope note P0-07)

**Question:** does a published open tool already do decision-level freshness, plus applicability gating, plus cost-optimal restoration, with a benchmark?

**Draft verdict: not found; continue, with caveats.** In the search results, no single work combined all four elements. Assurance-case change-impact tools cover decision-level impact but are qualitative and were described as over-approximate. Continuous digital-twin validation covers model-vs-data checks but not claims or planning. UQ and RTS work covers pieces in isolation. I found no ILP or other cost-optimal restoration planning for engineering evidence, and no public benchmark of controlled engineering changes with ground truth.

**Why this is weak evidence:** (a) I read abstracts and landing pages, not full papers; a paper may do more than its abstract says. (b) Google Scholar, IEEE Xplore, ACM DL and Scopus were not searched, only a general web search. (c) The strings on "model credibility AND automat*", "truth maintenance AND engineering design", and "validation envelope OR validity domain" were covered only indirectly. (d) The ExplicitCase, ReASSURE and AdvoCATE capabilities were not read in detail. The owner should read MMINT-A, ExplicitCase, Abeywickrama et al., and Mertens and Denil in full, and ideally get a second opinion from a practitioner, before recording the outcome.

## Gaps and cautions

- Several rows have partial citations (authors, venue or year not retrieved); these are marked in the `notes` column. The OpenModelica traceability row (MDPI 10(8):983) has an unconfirmed title and authors.
- Not found in search: any 2026 dedicated paper matching the dropped items in `docs/01` section 2.9. This does not prove they do not exist.
- Suggested next searches: the ReASSURE methodology, SysML v2 / MBSE change impact on simulation evidence, ML-pipeline staleness tools (DVC, MLflow papers), and test selection for simulation-based testing in IEEE Xplore and ACM DL.
