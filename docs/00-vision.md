# 00 — Vision

> **Git tells engineers what changed. ReVal tells them which engineering conclusions must be proven again — and the cheapest way to prove them.**

## The one-paragraph pitch

Engineering decisions ("this motor can run duty cycle DC-07 without the magnet exceeding 120 °C") rest on
evidence: measurements, simulations, ML predictions, analytical checks. That evidence was produced under
specific conditions — a dataset version, a model version, a coolant assumption, an operating envelope.
When any of those change, some conclusions silently lose their support and others are unaffected. Today
engineers either re-run everything (slow, expensive) or re-run what they *think* is affected (unsafe).
ReVal is an open-source, local-first tool that tracks the dependency between **claims**, **evidence**,
and **artifacts**, detects which claims a change actually affects, decides — deterministically — whether
each claim is still **Supported**, **Stale**, **Inconclusive**, or **Violated**, and computes a
**minimum-cost revalidation plan** to restore support.

## Who it helps

| User | Pain today | What ReVal gives them |
|---|---|---|
| Design / test engineer | "Which of my 40 thermal sign-offs survive the new coolant spec?" | A status board + the exact evidence that went stale and why |
| ML-for-engineering practitioner | Surrogate model used outside the region it was validated on | Applicability-domain gating: "prediction below limit, but out of envelope → not accepted" |
| Test lab / V&V lead | Bench time is expensive; full regression campaigns after every change | A cost-optimal plan that reuses still-valid evidence |
| Student / researcher | No open, reproducible workflow for decision-level V&V | A pip-installable SDK, a CLI, a CI action, and a public benchmark |

## What ReVal is NOT

- **Not a certification tool.** ReVal reports the *state of evidence*; it never claims a design is "safe".
  Every report carries that disclaimer.
- **Not a chatbot.** All validity judgments are deterministic, reproducible computations. An LLM may later
  *explain* a report or *draft* claim metadata for human review; it never decides a status.
- **Not a CAD/PDF understander.** Engineering metadata is declared explicitly (a manifest + Python
  decorators). Automatic extraction is out of scope for the capstone.
- **Not a generic digital twin or a SPDM platform.** It is a narrow, sharp layer that sits on top of an
  engineer's existing Python project and git history.

## Product shape (in priority order)

1. **`reval` Python library + CLI** — the core. `reval status`, `reval diff A B`, `reval plan --budget`, `reval run`, `reval report`.
2. **Motor-thermal reference project** (`examples/motor_thermal/`) — a real, data-backed engineering project that uses ReVal end to end.
3. **ReValBench** — a public benchmark of controlled engineering changes with ground truth, plus baselines. This is what turns the project into research.
4. **Web workspace** — FastAPI + React UI: claim board, change timeline, justification graph, envelope plots, planner with budget slider, exportable reports.
5. **CI integration** — a GitHub Action that comments on a PR: "this change makes 3 claims stale; cheapest plan: 2 tests, cost 14".

## Success criteria for the capstone

| # | Criterion | Measured by |
|---|---|---|
| S1 | The motor reference project runs end to end from a clean clone in < 30 min (excluding dataset download) | Scripted reproduction, CI |
| S2 | ReVal detects affected claims with recall ≥ 0.98 on Tier A, and on Tier B excluding T9 (undeclared drift, reported separately as a limitation). Missing an affected claim is the dangerous error. | Benchmark |
| S3 | Unsupported-accept rate (UAR_truth) is non-inferior to "rerun everything", **and** decision coverage stays within 2 pp of it | Benchmark, paired statistics |
| S4 | Revalidation cost is substantially lower than "rerun everything" and lower than file-level dependency tracking | Benchmark |
| S5 | Every assessment is bit-for-bit reproducible from its stored snapshot | Hash check over all benchmark runs |
| S6 | A non-author can install the library and add ReVal to a small project in under one hour | Docs + 3–5 person usability check |

Targets in S2–S4 are hypotheses. If the benchmark refutes them, an honest negative result, properly analyzed, is still a valid capstone outcome.

## The research question

> **Can change-aware, tolerance-aware evidence dependency analysis reduce engineering revalidation cost
> without increasing the rate at which unsupported decisions are accepted?**

The sub-questions (RQ1–RQ5) and how they are measured are in [06-evaluation.md](06-evaluation.md).

## Changes from the original Codex concept

The original idea is good. This plan keeps its core and changes the following:

1. **Formal grounding.** ReVal's invalidation logic is a *truth-maintenance system* (Doyle 1979; de Kleer 1986)
   combined with *build-system early cutoff* (Mokhov et al. 2018) and *regression test selection* (Gligoric et al. 2015).
   Naming these lineages makes the novelty claim precise and the related-work section honest.
2. **Assurance cases and ASME V&V 40** are added to the prior-art map. Risk-informed credibility (V&V 40) becomes
   ReVal's *evidence policy* mechanism: higher-consequence requirements need stronger evidence.
3. **Claims are about duty cycles, not static points.** Motor temperature is a dynamic thermal state. A claim like
   "T_pm ≤ 120 °C at torque X" means nothing without a load history. Claims are stated over parameterized duty cycles.
4. **An independent physics simulator** (a lumped-parameter thermal network, LPTN) is the second evidence source,
   next to the ML model. Agreement between independent sources is part of the evidence policy.
5. **Tolerance-aware invalidation** is the specific technical contribution: a change only invalidates evidence if it
   touches the evidence's declared scope *and* exceeds a justified sensitivity bound. Without it, ReVal would be just
   a file-dependency tracker. With it comes a safety risk, which the benchmark measures.
6. **The planner is an ILP over policy alternatives**, not plain set cover. One bench run can discharge obligations for
   several claims, and a claim can be restored by different evidence combinations.
7. **Two-tier evaluation.** Tier A *truth* is real measured data only (held-out test profiles). Tier B uses a "virtual world"
   thermal model with injected physical changes (for example, a cooling change), which gives controllable ground truth. The two tiers
   are reported separately and are never mixed.
8. **CLI- and library-first, git-native.** Snapshots map to git commits. The web UI is a view over the same engine.
   This is what makes the tool useful to people outside the capstone.
