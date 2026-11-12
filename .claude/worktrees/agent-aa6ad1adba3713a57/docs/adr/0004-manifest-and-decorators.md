# ADR 0004 — Explicit metadata: `reval.yaml` manifest + `@reval.producer` decorators

- **Status:** accepted
- **Date:** 2026-10-24

## Context
ReVal needs requirements, assumptions, claims, subjects, and producer dependencies. They could be inferred (from notebooks, CAD,
or PDFs), but inference is unreliable and unreviewable.

## Decision
Declarative entities (artifacts, assumptions, requirements, subjects, claims, policies) live in `reval.yaml`, versioned with the project.
Executable evidence producers are Python functions registered with `@reval.producer(...)`, which declare dependencies (field-level
selectors), assumptions, cost, and kind. `Context.load()` enforces the declared dependencies at runtime.

## Consequences
- Metadata changes show up in normal code review and git diffs.
- Adoption cost: users must write the manifest. `reval init` and a tutorial reduce it.
- A future, optional assistant could *propose* manifest entries for human approval (ADR 0001 still applies).
