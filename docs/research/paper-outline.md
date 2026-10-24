# Paper outline (working)

**Working title:** *Which Conclusions Survive a Change? Change-Aware, Tolerance-Aware Revalidation of Engineering Decisions*

**Candidate venues (check deadlines and fit with your supervisor):** ASME VVUQ Symposium, the MODELS conference or its workshops
(model-driven engineering, traceability), SE-for-CPS workshops at ICSE/ASE, an arXiv preprint first.

1. **Introduction:** the stale-evidence problem. A motor example. Contributions (C1–C4 from `docs/01` §3).
2. **Background & related work:** TMS, build systems / early cutoff, RTS, V&V credibility (V&V 40, NASA-STD-7009), assurance cases, conformal / applicability domain, PMSM thermal modeling.
3. **Model:** claims, evidence, policies, verdicts, four-valued status. Freshness classes and tolerance carry-forward. Invariants and soundness conditions (and what is *not* guaranteed).
4. **Revalidation planning:** ILP over policy alternatives. Budgeted variant. Complexity. Greedy baseline.
5. **Implementation:** architecture, SDK, git integration, determinism measures.
6. **Case study:** PMSM thermal (dataset, splits, models, LPTN, AD, conformal coverage, optimizer O1–O3).
7. **ReValBench:** change taxonomy, oracles, Tier A vs. Tier B.
8. **Results:** RQ1–RQ4 (RQ5 if run). Per-change-type tables. Ablations. Cost sensitivity.
9. **Threats to validity.**
10. **Limitations & future work:** undeclared drift (T9) → monitoring, multi-domain, assistant-proposed metadata.
11. **Conclusion.**

Artifact availability statement: code, benchmark generator, configs, and result hashes are public. The dataset is linked, not redistributed.
