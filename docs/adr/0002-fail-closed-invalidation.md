# ADR 0002 — Fail-closed invalidation

- **Status:** accepted
- **Date:** 2026-10-24

## Context
The dangerous error is accepting a claim whose support was silently invalidated. Over-invalidation only costs extra tests.

## Decision
Evidence is fresh only if a positive rule proves it (exact hash match, out-of-scope rows, or declared tolerance within range).
Unknown change kinds, undeclared dependencies, missing tolerances, and whole-artifact (`*`) dependencies on a changed artifact
invalidate. The producer SDK raises if a producer reads an artifact it didn't declare.

## Consequences
- Impact recall should be very high. Precision depends on how much scope and tolerance metadata users declare.
- Invariant I3: removing metadata can never move a claim toward acceptance.
- Undeclared physical drift (benchmark T9) can't be detected from a change set. That's a documented limitation.
