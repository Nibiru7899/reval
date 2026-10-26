# ADR 0002 — Fail-closed invalidation

- **Status:** accepted
- **Date:** 2026-10-24

## Context
The dangerous error is accepting a claim whose support was silently invalidated. Over-invalidation only costs extra tests.

## Decision
Evidence is fresh only if a positive rule proves it (exact hash match, out-of-scope rows through a column-selector dependency, or a declared tolerance
with old and new values in range). These always invalidate:
- unknown change kinds;
- undeclared dependencies and missing tolerances;
- whole-artifact (bare `art`, written `*`) dependencies on a changed artifact;
- a change of the evidence's subject;
- an upstream change of a derived artifact (every hasher folds `derived_from` hashes);
- a missing old snapshot.

The producer SDK raises if a producer reads an artifact it didn't declare as a whole or by columns. Assumptions declared by the producer are always part of the evidence's scope.
Losing FAIL evidence to a change makes the claim STALE, never SUPPORTED (`docs/03` §3 rule 3).

*Amended 2026-10-26 (audit decisions D2, D3, D4, D9, D11, D12).*

## Consequences
- Impact recall should be very high. Precision depends on how much scope and tolerance metadata users declare.
- Invariant I3: removing metadata can never move a claim toward acceptance.
- Undeclared physical drift (benchmark T9) can't be detected from a change set. That's a documented limitation.
