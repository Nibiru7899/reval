# FAQ and limitations

## Is ReVal a certification or safety tool?

No. ReVal reports **the state of recorded evidence against a declared requirement**. It never says a design is safe, certified, or verified to a
standard. The default evidence policies are risk-informed in spirit, inspired by ASME V&V 40, and are explicitly not an implementation of it. Every report
carries the sentence *"ReVal reports the state of recorded evidence against declared requirements. It does not certify safety."*

## What can ReVal not detect? (T9: undeclared drift)

ReVal reasons from **declared** change: the difference between two snapshots of tracked artifacts, assumptions, requirements and producer code.
If the physical world changes without any tracked artifact changing (a winding resistance rises with ageing, a sensor drifts, a supplier changes a material),
old evidence still looks fresh, because nothing ReVal can see changed. The benchmark's change type **T9** exists to measure exactly this: a change in
the simulated world with no declared parameter change. The evaluation plan states that nothing can detect it from the change set alone, reports it separately,
and treats it as a limitation. Monitoring is the complement, not something ReVal replaces. See [evaluation, section on limitations](../06-evaluation.md).

## Why did my claim become STALE instead of VIOLATED or SUPPORTED?

`STALE` means support (or a refutation) existed and a change invalidated it. A previously failing claim whose failing evidence is invalidated becomes `STALE`,
never `SUPPORTED`: a change cannot launder a failure. Run `reval plan` to see which runs would restore a verdict, and `reval explain <claim>` for the reasons.
Rules: [Concepts](concepts.md#status-rules).

## Why is an ML prediction INCONCLUSIVE?

Either it is outside its applicability domain (every out-of-domain case is inconclusive), or its conformal interval straddles the limit
(`margin_below_uncertainty`), or the policy needs an independent second source that is missing (`policy_unmet`).

## Why was my evidence invalidated by a tiny change?

Fail closed. If a producer reads a parameter and declares no tolerance for it, any change to that parameter invalidates the evidence. Declare a `Tolerance`
(sensitivity, valid range, backing assumption) if you can justify one, and declare dependencies at field level rather than on a whole file.

## Does a language model decide anything?

No. `reval.core` is deterministic and pure; no language model ever decides a status. Models may only draft metadata for human review or paraphrase a finished report,
behind an explicit flag and outside the core.

## What is stored, and can I edit it?

Evidence and assessments are append-only in the project's local store (`.reval/`, SQLite by default). New information means new records. The store is
git-ignored; `reval.lock.json` (the snapshot hashes) is what you commit.

## Is the data split safe?

For the motor example, splits are by `profile_id` and defined in `examples/motor_thermal/splits.yaml`; calibration and test profiles are never used for fitting.
Splitting by random rows would leak, because rows of one profile are highly autocorrelated.

## What is the project status?

A personal research project with no institution behind it. The version is 0.0.x, the API is not frozen, and the license has not been chosen yet
("TBD"; the owner decides at release). The roadmap is in [07 Roadmap](../07-roadmap.md), the risk register in [08 Risks](../08-risks.md).
