# 03 — Domain model and status semantics

This document is the **contract** for `src/reval/domain/` and `src/reval/core/status.py`. Code must match it.
Change the code and this document in the same PR.

## 1. Entities

| Entity | Key fields | Notes |
|---|---|---|
| `Artifact` | `id`, `kind` (`dataset` \| `model` \| `params` \| `code` \| `document`), `path`, `hasher` | Logical identity. Stays stable across versions. |
| `ArtifactVersion` | `artifact_id`, `content_hash`, `field_hashes: {selector: hash}`, `meta` | Immutable. `field_hashes` enable field-level diffs. |
| `Assumption` | `id`, `statement`, `variable`, `unit`, `bounds` or `value ± tol` | Declared engineering assumption (for example, coolant inlet 18–70 °C). Versioned like an artifact. |
| `Requirement` | `id`, `text`, `quantity`, `op` (`<=` \| `>=`), `limit`, `unit`, `criticality` (`low` \| `medium` \| `high`) | Machine-checkable predicate over a quantity. |
| `Subject` | `id`, `kind` (`duty_cycle` \| `design` \| `operating_point`), `params` | What a claim is about. A duty cycle is a parameterized load profile. |
| `Claim` | `id`, `requirement_id`, `subject_id`, `policy_id` | "Subject satisfies requirement". The policy defaults to the requirement's criticality tier. |
| `Producer` | `id`, `kind` (`ml_prediction` \| `physics_sim` \| `measurement` \| `analytic` \| `waiver`), `code_hash`, `cost_model`, `fidelity` | A function that can create evidence. Registered via `@reval.producer`. |
| `Evidence` | `id`, `producer_id`, `subject_id`, `quantity`, `result` (point, interval, verdict inputs), `deps: [Dependency]`, `scope`, `tolerances`, `provenance`, `cost`, `created_at` | Immutable once stored. |
| `Dependency` | `artifact_id`, `selector` (JSON pointer / column set / `*`), `version_hash` | Field-level. `selector="*"` means the whole artifact (coarse, safe default). |
| `Scope` | `box: {variable: [lo, hi]}`, `assumption_values` | The region and conditions over which the evidence is claimed to hold. |
| `Tolerance` | `selector`, `sensitivity` (output units per input unit), `valid_range`, `safety_factor κ`, `source` | A declared bound used for tolerance-aware carry-forward. `source` must cite how it was obtained (for example, "finite differences on LPTN v3, grid G2"). |
| `Policy` | `id`, `alternatives: [[EvidenceRequirement]]` | Disjunctive normal form: OR over clauses, AND within a clause. |
| `EvidenceRequirement` | `kind`, `min_fidelity`, `in_domain: bool`, `independent_of: [kind]` | One conjunct. |
| `Snapshot` | `id` (Merkle root), `git_rev?`, `artifact_versions`, `manifest_hash` | The project state. |
| `ChangeSet` | `from`, `to`, `changes: [Change]` | `Change` = `FieldChanged` \| `RowsAdded` \| `RowsModified` \| `ArtifactAdded/Removed` \| `RequirementChanged` \| `AssumptionChanged` \| `ProducerCodeChanged` \| `Unknown`. |
| `Assessment` | `claim_id`, `snapshot_id`, `status`, `reasons: [Reason]`, `evidence_used`, `input_hash` | Pure function output. |
| `RevalidationPlan` | `snapshot_id`, `runs: [PlannedRun]`, `total_cost`, `objective`, `solver_status`, `unrestorable: [claim_id]` | |

## 2. Evidence verdicts

Every fresh evidence item is reduced to a three-valued **verdict** against a claim's requirement (shown here for `op = "<="`, limit *L*):

| Producer kind | Interval used | pass | fail | inconclusive |
|---|---|---|---|---|
| `measurement` | measured peak ± sensor uncertainty *u* | ŷ + u ≤ L | ŷ − u > L | otherwise |
| `ml_prediction` | conformal interval [lo, hi] at level 1−α | in domain ∧ hi ≤ L | in domain ∧ lo > L | otherwise, **including every out-of-domain case** |
| `physics_sim` | ŷ ± model-form band δ (from validation residuals) | ŷ + δ ≤ L | ŷ − δ > L | otherwise |
| `analytic` | exact value or declared bound | value ≤ L | value > L | — |
| `waiver` | — | always pass, with mandatory justification + author | — | — |

Carried-forward evidence (§4) uses its *inflated* interval.

## 3. Claim status (four values + waived)

Evaluated in this order. The first rule that matches wins:

1. **VIOLATED.** Some fresh, policy-eligible evidence has verdict `fail`. Fail dominates. If other evidence passes, the reason is `CONFLICTING_EVIDENCE` and an engineer must investigate.
2. **WAIVED.** A fresh `waiver` evidence item exists. (A waiver depends on the claim's full dependency cone, so any upstream change makes it stale automatically.)
3. **SUPPORTED.** Some policy clause has every conjunct satisfied by distinct fresh evidence with verdict `pass`, meeting the clause's `in_domain`, `min_fidelity`, and `independent_of` constraints.
4. **STALE.** Not supported now, *but* a clause was satisfied in the previous assessment and at least one evidence item it used is no longer fresh. (Support was lost because of a change.)
5. **INCONCLUSIVE.** Everything else: no evidence (`NO_EVIDENCE`), out of domain (`OUT_OF_DOMAIN`), interval straddles the limit (`MARGIN_BELOW_UNCERTAINTY`), missing independent source (`POLICY_UNMET`), and so on.

Only **SUPPORTED** and **WAIVED** count as "accepted" in metrics.

### Default policies (risk-informed, inspired by ASME V&V 40 — not an implementation of it)

Shorthand: `kind{constraints}`. A clause is a list of conjuncts. A policy is a list of clauses.

```
low:    [ml_prediction{in_domain}] | [physics_sim] | [measurement]
medium: [ml_prediction{in_domain}, physics_sim{independent_of: ml_prediction}] | [measurement]
high:   [measurement] | [physics_sim{min_fidelity: 2}, ml_prediction{in_domain, independent_of: physics_sim}]
```

The manifest uses the structured form (`[{kind: ml_prediction, in_domain: true}, …]`). See `docs/10-interfaces.md` §3.

**Independence:** two evidence items are independent iff they have different `producer_kind` **and** their sets of `model`-kind artifact
dependencies are disjoint.

## 4. Freshness and carry-forward

Evidence *e* recorded at snapshot *S*. Moving to snapshot *S′* with change set Δ:

- **Fresh (exact):** every dependency `(artifact, selector, version_hash)` of *e* has an identical hash in *S′*, the producer code hash is unchanged, and every assumption in `e.scope.assumption_values` still holds in *S′*.
- **Fresh (out of scope):** every changed dependency is a `RowsAdded`/`RowsModified` change whose affected rows lie entirely outside `e.scope.box` **and** *e* does not depend on an artifact derived from those rows (for example, a model retrained on them). Derived-artifact edges are followed transitively.
- **Carried forward (tolerance):** every changed field *f* has a declared `Tolerance` with Δf inside `valid_range`. The evidence interval is then inflated by `Σ_f κ_f · s_f · |Δf|`, and the result is recorded as a new derived evidence item that points back to *e*. The inflated interval may still pass, may now be inconclusive, or may even fail.
- **Not fresh:** anything else. **`Unknown` changes, missing tolerances, and `selector="*"` dependencies on a changed artifact always invalidate.**

Each tolerance is itself backed by an `Assumption` node ("sensitivity of peak T_pm to coolant flow ≤ 1.9 K/(L/min) over 4–10 L/min"),
so a change to the thing that justified the bound invalidates the bound.

## 5. Invariants (each one becomes a property-based test in `tests/property/`)

- **I1 Determinism.** `assess(S)` returns identical assessments and an identical `input_hash` across runs, processes, and machines.
- **I2 Locality.** A change to an artifact outside a claim's dependency cone never changes that claim's status.
- **I3 Fail-closed.** Replacing any declared tolerance or scope with "undeclared" never moves a claim *toward* acceptance.
- **I4 No free support.** For a fixed policy and requirement, a change with no new evidence never moves a claim from non-accepted to accepted. (Loosening a requirement *can* legitimately do this. It is a `RequirementChanged` and is reported as such.)
- **I5 Monotone inflation.** A larger |Δf| never yields a narrower carried-forward interval.
- **I6 Plan soundness.** If every planned run returns a decisive verdict, every claim not listed as unrestorable reaches a decided status (Supported, Violated, or Waived).
- **I7 Exact-fresh idempotence.** `assess(S)` after `diff(S, S)` equals `assess(S)`.

## 6. Manifest sketch (`reval.yaml`)

```yaml
version: 1
project: motor-thermal

artifacts:
  measures:   {kind: dataset, path: data/processed/measures.parquet, hasher: dataframe, key: [profile_id, t]}
  drive_map:  {kind: model,   path: models/drive_map.joblib, derived_from: [measures]}
  tpm_model:  {kind: model,   path: models/tpm_ridge.joblib, derived_from: [measures]}
  lptn:       {kind: params,  path: params/lptn.yaml, hasher: yaml-fields}
  cooling:    {kind: params,  path: params/cooling.yaml, hasher: yaml-fields}

assumptions:
  A-coolant-range: {variable: coolant, unit: degC, bounds: [18, 70]}
  A-sensor-pm:     {variable: pm_sensor_uncertainty, unit: K, value: 2.0}

requirements:
  R-PM-MAX:  {text: "Magnet temperature shall not exceed the declared limit", quantity: pm_peak, op: "<=", limit: 110, unit: degC, criticality: high}
  R-SW-MAX:  {text: "Stator winding temperature shall not exceed the declared limit", quantity: sw_peak, op: "<=", limit: 130, unit: degC, criticality: medium}
  R-SHAFT-D: {text: "Shaft diameter within tolerance", quantity: shaft_d, op: "<=", limit: 30.05, unit: mm, criticality: low}

subjects:
  DC-07: {kind: duty_cycle, generator: motor.cycles:blocks, params: {blocks: [[120, 4000, 600], [60, 2500, 900]], coolant: 45, ambient: 25}}

claims:
  - {id: C-DC07-PM, requirement: R-PM-MAX, subject: DC-07}
  - {id: C-DC07-SW, requirement: R-SW-MAX, subject: DC-07}

producers: motor.producers   # module that registers @reval.producer functions
```

(The limits above are placeholders. The study's declared limits are chosen after EDA; see [05-motor-domain.md](05-motor-domain.md).)

## 7. Producer SDK sketch

```python
import reval

@reval.producer(
    kind="ml_prediction",
    quantity="pm_peak",
    cost=1,
    depends_on=["tpm_model", "drive_map", "cooling#/coolant/inlet_temp"],
    assumes=["A-coolant-range"],
)
def predict_pm_peak(subject: reval.Subject, ctx: reval.Context) -> reval.Evidence:
    traj = ctx.load("drive_map").to_trajectory(subject)
    model = ctx.load("tpm_model")
    lo, hi, point = model.predict_peak_interval(traj, alpha=0.1)
    ad = model.domain.check(traj)                    # applicability-domain report
    return reval.Evidence.interval(point=point, lo=lo, hi=hi, unit="degC",
                                   in_domain=ad.inside, domain_report=ad.summary(),
                                   scope=reval.Scope.box_of(traj))
```

The decorator records the code hash (SHA-256 of the defining module's source file plus the function's qualified name, a conservative
choice: any edit to the module invalidates), the declared dependencies, and the cost.
`ctx.load` **raises** if code tries to read an artifact it didn't declare. This keeps dependency declarations honest
(the dynamic-dependency idea from Ekstazi, enforced at the SDK boundary).

## 8. Persistence (relational sketch)

Document tables: each row has indexed key columns plus `body` (the canonical JSON of the domain object). Tables: `snapshots(id, git_rev,
created_seq)`, `evidence(id, subject_id, producer_id, snapshot_id)`, `assessments(snapshot_id, claim_id, status, input_hash)`,
`plans(id, snapshot_id)`, `jobs(id, kind, state, payload, result)`, `reports(id, snapshot_id)`. Evidence and assessments are
append-only. Nothing is updated in place, except `jobs.state`. Full column list: `docs/10-interfaces.md` §8.
