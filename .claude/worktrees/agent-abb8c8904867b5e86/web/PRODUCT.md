# Product

<!-- impeccable:product-schema 1 -->

> Written by an orchestrated subagent with no live answer channel. Facts come from the repository
> (`AGENTS.md`, `docs/00-vision.md`, `docs/03-domain-model.md`, `docs/09-api-and-ui.md`) and the owner's
> brief. Items marked *(inferred)* were not confirmed by the owner.

## Platform

web

## Users

Design and test engineers who own an engineering project (reference: thermal validation of a permanent-magnet
synchronous motor). They open the workspace after a change lands (new data, a model retrain, a parameter or
requirement edit) to see which engineering claims are still supported by fresh evidence and what to re-run.
Sessions are short and frequent, at a desk, next to a terminal and a git client *(inferred)*.

## Product Purpose

ReVal is a continuous validation engine for engineering decisions. Given a change, it determines which claims are
supported, stale, inconclusive, violated or waived, why, and the minimum-cost set of tests that restores support.
Success: an engineer can answer "what does this change put at risk, and what do I run?" in seconds, and trust the answer.

## Positioning

Status is computed deterministically from recorded evidence, freshness rules and declared tolerances, never by a
language model, and it fails closed: unknown changes invalidate evidence rather than defaulting to fresh.

## Operating Context

A local single-project server (`reval serve`) with a CLI twin (`reval status`, `diff`, `plan`, `explain`, `report`).
Snapshots are content hashes tied to git revisions. The UI is read-mostly; planning and execution are explicit actions.

## Capabilities and Constraints

- Statuses: supported, waived, stale, inconclusive, violated. Reasons are machine codes with messages.
- Every claim has a requirement (with criticality), a subject, and evidence with freshness classes.
- Status is never signalled by colour alone: icon and text label always accompany it.
- Generated API client only; no hand-written API types.

## Brand Commitments

- Honest language: never "safe", "certified" or "verified to standard X". Say "supported by recorded evidence
  against the declared requirement". Reports carry the disclaimer
  "ReVal reports the state of recorded evidence against declared requirements. It does not certify safety."
- Owner asked for a beautiful, not bare, workspace: dense, trustworthy, calm, precise.

## Evidence on Hand

Real projects: `examples/motor_thermal` (Paderborn dataset) and `examples/beam_toy`. No customers, testimonials or benchmarks
may be invented.

## Product Principles

1. The reason matters as much as the status: always show why.
2. Fail closed, and show that it did.
3. Every number traces to a snapshot hash and a git revision.
4. Calm by default; alarm only where the evidence says so.

## Accessibility & Inclusion

Colour-blind-safe status encoding with paired icons and labels; keyboard operable tables; WCAG AA contrast *(inferred standard)*.
