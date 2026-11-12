# Design documents

The numbered documents under `docs/` are the design record and **the contract** for the implementation. They are linked here, not duplicated.

| Document | What it fixes |
|---|---|
| [00 Vision](../00-vision.md) | Scope, users, non-goals, success criteria, research question |
| [01 Problem and prior art](../01-problem-and-prior-art.md) | The formal problem and related work |
| [02 Architecture](../02-architecture.md) | Layers, engines, repository layout |
| [03 Domain model](../03-domain-model.md) | Entities, verdicts, status rules, freshness, invariants, reason codes, manifest |
| [04 Algorithms](../04-algorithms.md) | Hashing, impact analysis, applicability domain, conformal intervals, the planner ILP |
| [05 Motor domain](../05-motor-domain.md) | Dataset, splits, models, the lumped-parameter thermal network, producers |
| [06 Evaluation](../06-evaluation.md) | Research questions, ReValBench, metrics, baselines, statistics |
| [07 Roadmap](../07-roadmap.md) | Phases, milestones, cut lines |
| [08 Risks](../08-risks.md) | Risk register |
| [09 CLI, API and UI](../09-api-and-ui.md) | Interfaces and the report format |
| [10 Interfaces](../10-interfaces.md) | Binding module signatures |

!!! info "When docs and code disagree"
    `03-domain-model.md` is the contract: if you change a status, a freshness rule, a verdict rule or an invariant,
    that file changes in the same commit, together with a property test. The pages in this site describe the
    behaviour of the current code and were checked by running it.
