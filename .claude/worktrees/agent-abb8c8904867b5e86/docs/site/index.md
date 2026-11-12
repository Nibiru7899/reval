---
title: Continuous validation
hide:
  - navigation
  - toc
---

<div class="hero" markdown>

# Which engineering conclusions survive a change?

<p class="tagline">
Git tells you what changed. ReVal tells you which <strong>claims</strong> about your design are still supported by
fresh evidence, which went stale, and the cheapest set of tests that restores the rest.
</p>

[Quickstart](quickstart.md){ .md-button .md-button--primary }
[Add it to your project](tutorial-new-project.md){ .md-button }

</div>

## What it does

You change a parameter, retrain a surrogate, tighten a requirement or update an assumption. Somewhere there is a claim such as
*"duty cycle DC-07 keeps the magnet below 90 degC"*, and some evidence behind it (a measurement, a simulation, an ML prediction)
that was recorded before your change. ReVal tracks that dependency chain and reassesses every claim:

<div class="grid cards" markdown>

-   :material-check-circle:{ .lg } **Supported**

    Fresh evidence satisfies the claim's evidence policy.

-   :material-clock-alert:{ .lg } **Stale**

    It was supported, but the change invalidated evidence it relied on.

-   :material-help-circle:{ .lg } **Inconclusive**

    The evidence is insufficient: out of the model's validated domain, an interval that straddles the limit, or a missing independent source.

-   :material-close-circle:{ .lg } **Violated**

    Fresh evidence shows the requirement is not met.

</div>

Then it computes a **minimum-cost revalidation plan** (an integer program solved with OR-Tools) that reuses every piece of
evidence that is still valid and re-runs only what is needed.

## Why you can trust the machinery

- **Deterministic and pure core.** The engines in `reval.core` do no I/O, read no clocks and call no language model. The same snapshot and
  evidence always give the same statuses. No language model ever decides a status.
- **Fail closed.** An unknown kind of change, an undeclared dependency, a missing tolerance, or a wildcard on a changed artifact
  *invalidates* evidence. There is no code path that defaults to "still fresh".
- **Append-only records.** Evidence and assessments are never edited or deleted. New information means new records.
- **Every number is reproducible.** Reported numbers come from committed scripts.

## See it in ten minutes

```console
$ reval run --all
ran 6 producer results
CLAIM      BEFORE        AFTER      CLAUSE
C-S1-HI    INCONCLUSIVE  SUPPORTED  0
C-S1-TEMP  INCONCLUSIVE  SUPPORTED  0
C-S2-TEMP  INCONCLUSIVE  VIOLATED   -
C-SHAFT    INCONCLUSIVE  SUPPORTED  3
```

That is the bundled mini project (see the [quickstart](quickstart.md)). The [motor tutorial](motor-tutorial.md) does the same on a real
permanent-magnet synchronous motor dataset, and [Add ReVal to your project](tutorial-new-project.md) builds a new project from an empty folder.

!!! warning "Honest language: what ReVal does not say"
    ReVal reports **the state of recorded evidence against a declared requirement**. It does **not** say that a design is safe,
    certified, or verified to any standard, and it does not replace engineering judgement, a safety case, or a certification process.
    Limits in the examples are study parameters, not manufacturer ratings. Every generated report carries this disclaimer.

    ReVal also cannot see what nobody declared: a physical change that is not recorded in a tracked artifact (for example
    wear that raises a resistance) leaves old evidence looking fresh. See [FAQ and limitations](faq.md).

## Where to go next

| I want to... | Go to |
|---|---|
| install it and run one command | [Quickstart](quickstart.md) |
| understand claims, evidence, freshness and status | [Concepts](concepts.md) |
| put it on my own project | [Add ReVal to your project](tutorial-new-project.md) |
| see the full motor story with real numbers | [Motor tutorial](motor-tutorial.md) |
| look up a command or a function | [CLI](cli.md), [Python API](api.md) |
| read the design record or the evaluation plan | [Design docs](design-docs.md), [Research](research.md) |
