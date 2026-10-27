# Paper outline (working)

**Working title:** *Which Conclusions Survive a Change? Change-Aware, Tolerance-Aware Revalidation of Engineering Decisions*

**Candidate venues (optional; check deadlines and fit yourself):** ASME VVUQ Symposium, the MODELS conference or its workshops
(model-driven engineering, traceability), SE-for-CPS workshops at ICSE/ASE, an arXiv preprint first.

1. **Introduction:** the stale-evidence problem. A motor example. Contributions (C1–C4 from `docs/01` §3).
2. **Background & related work:** TMS, build systems / early cutoff, RTS, V&V credibility (V&V 40, NASA-STD-7009), assurance cases, conformal / applicability domain, PMSM thermal modeling.
3. **Model:** claims, evidence, policies, verdicts, five-valued claim status (four in benchmarks, which contain no waivers). Freshness classes and tolerance carry-forward. Invariants and soundness conditions (and what is *not* guaranteed).
4. **Revalidation planning:** ILP over policy alternatives. Budgeted variant. Complexity. Greedy baseline.
5. **Implementation:** architecture, SDK, git integration, determinism measures.
6. **Case study:** PMSM thermal (dataset, splits, models, LPTN, AD, conformal coverage, optimizer O1–O3).
7. **ReValBench:** change taxonomy, oracles, Tier A vs. Tier B.
8. **Results:** RQ1–RQ4 (RQ5 if run). H1 as an intersection–union test (cost, UAR_truth, UAR_evidence, decision coverage). Per-change-type tables. Ablations A1–A8. Cost sensitivity. Tier A and Tier B reported separately. RQ4's 2×2 optimizer × acceptance design is Tier B only.
9. **Threats to validity:** shared LPTN model-form error between physics evidence and tolerance bounds, world-model circularity, assumed costs, one domain, the T9 blind spot.
10. **Limitations & future work:** undeclared drift (T9) → monitoring, multi-domain, assistant-proposed metadata.
11. **Conclusion.**

Artifact availability statement: code, benchmark generator, configs, and result hashes are public. The dataset (CC BY-SA 4.0) is linked, not redistributed, and no derived data is published. The analysis plan was pre-registered at the end of week 21.
