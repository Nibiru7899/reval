# ReVal — continuous validation for engineering decisions

> Git tells engineers what changed. ReVal tells them which engineering conclusions must be proven again — and the cheapest way to prove them.

An engineer changes a design parameter, retrains a surrogate model, tightens a requirement, or updates a coolant assumption.
ReVal tracks how every engineering **claim** ("duty cycle DC-07 keeps the magnet below 110 °C") depends on **evidence**
(measurements, simulations, ML predictions) and how that evidence depends on versioned **artifacts**. After a change, it reports
each claim as one of:

| Status | Meaning |
|---|---|
| ✅ **Supported** | Fresh evidence satisfies the claim's evidence policy |
| 🕓 **Stale** | It was supported, but the change invalidated evidence it relied on |
| ❔ **Inconclusive** | Evidence is insufficient: out of the model's validated domain, uncertainty straddles the limit, or a required independent source is missing |
| ⛔ **Violated** | Fresh evidence shows the requirement isn't met |

ReVal then computes a **minimum-cost revalidation plan** (an ILP solved with OR-Tools) that reuses evidence still valid.
All judgments are deterministic and reproducible. ReVal reports the state of the evidence. It does **not** certify safety.

**Project status:** planning / Phase 0 (capstone project). See the [roadmap](docs/07-roadmap.md).

## Documentation

| Doc | Contents |
|---|---|
| [00 Vision](docs/00-vision.md) | Pitch, users, non-goals, success criteria, research question |
| [01 Problem & prior art](docs/01-problem-and-prior-art.md) | Formal problem, related work, review protocol |
| [02 Architecture](docs/02-architecture.md) | Layers, engines, design decisions, repo layout |
| [03 Domain model](docs/03-domain-model.md) | Entities, verdicts, status rules, freshness, invariants, manifest |
| [04 Algorithms](docs/04-algorithms.md) | Hashing, impact, applicability domain, conformal, planner ILP |
| [05 Motor domain](docs/05-motor-domain.md) | Dataset, splits, models, LPTN, producers, virtual world |
| [06 Evaluation](docs/06-evaluation.md) | RQs, ReValBench, metrics, baselines, ablations, statistics |
| [07 Roadmap](docs/07-roadmap.md) | 30-week plan, milestones, cut lines, 16-week variant |
| [08 Risks](docs/08-risks.md) | Risk register |
| [09 CLI, API & UI](docs/09-api-and-ui.md) | Interfaces and report format |
| [ADRs](docs/adr/) | Architecture decision records |
| [AGENTS.md](AGENTS.md) | Rules for contributors and AI coding agents |

## Development

```bash
uv sync --all-extras
uv run pytest
uv run reval --help
```

Without uv: `python -m venv .venv`, activate it, then `pip install -e ".[dev]"`.

## Data and acknowledgements

The reference domain uses the *Electric Motor Temperature* dataset by the Department of Power Electronics and Electrical Drives (LEA),
Paderborn University (Kaggle: `wkirgsn/electric-motor-temperature`), and builds on the thermal-modeling work of W. Kirchgässner,
O. Wallscheid and J. Böcker. The data is not redistributed here. It is downloaded by script under its own license.

## License

To be decided. Check your institution's capstone IP policy first. Apache-2.0 is recommended for an open engineering tool.
