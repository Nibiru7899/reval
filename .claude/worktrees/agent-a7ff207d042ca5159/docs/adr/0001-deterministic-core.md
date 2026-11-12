# ADR 0001 — Deterministic core; no LLM in validity judgments

- **Status:** accepted
- **Date:** 2026-10-24

## Context
ReVal's value is that its statuses can be trusted, reproduced, and audited. LLM-based agents are attractive for extracting claims
or explaining reports, but they are non-deterministic and can't be held to a soundness argument.

## Decision
`src/reval/core/` is a pure, deterministic library: no I/O, no clock, no unseeded randomness, no network, no LLM. Every assessment
records an `input_hash` over its inputs. LLM features, if ever added, live outside `core/`, behind a flag, and only produce drafts
for human review or paraphrases of finished reports.

## Consequences
- Property-based tests can check the invariants (I1–I7) directly.
- Reproducibility (S5) is achievable by construction.
- Claim extraction from free text is out of scope. Metadata is declared explicitly.
- An architecture test (`tests/unit/test_architecture.py`) fails if `core/` imports I/O, network, or LLM modules.
