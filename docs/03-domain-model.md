# 03 — Domain model and status semantics

This document is the **contract** for the meaning of `src/reval/domain/` and `src/reval/core/`. The exact shapes (field types, signatures) are in
[10-interfaces.md](10-interfaces.md) §2 and §4. Code must match both. Change the code, this document and `10-interfaces.md` in the same PR.
The rulings behind the current version are recorded in `docs/log/2026-10-26-audit-decisions.md` (D1–D27).

## 1. Entities

Field names match `10-interfaces.md` §2.

| Entity | Key fields | Notes |
|---|---|---|
| `Artifact` | `id`, `kind` (`dataset` \| `model` \| `params` \| `code` \| `document`), `path`, `hasher`, `derived_from`, `key` | Logical identity. Stays stable across versions. `derived_from` records the constructive trace. |
| `ArtifactVersion` | `artifact_id`, `content_hash`, `field_hashes`, `field_values`, `row_groups` | Immutable. `content_hash` folds in upstream hashes when `derived_from` is set (D3). `field_hashes` are own-only and enable field-level diffs. |
| `Assumption` | `id`, `statement`, `variable`, `unit`, `bounds` or `value ± tol` | Declared engineering assumption (for example, coolant inlet 18–70 °C). A change of any field is an `ASSUMPTION_CHANGED`. |
| `Requirement` | `id`, `text`, `quantity`, `op` (`<=` \| `>=`), `limit`, `unit`, `criticality` (`low` \| `medium` \| `high`) | Machine-checkable predicate over a quantity. |
| `Subject` | `id`, `kind` (`duty_cycle` \| `design` \| `operating_point`), `generator`, `params` | What a claim is about. A duty cycle is a parameterized load profile. |
| `Claim` | `id`, `requirement_id`, `subject_id`, `policy_id` | "Subject satisfies requirement". The policy defaults to the requirement's criticality tier. |
| `Producer` | `id`, `kind` (`ml_prediction` \| `physics_sim` \| `measurement` \| `analytic` \| `waiver`), `quantities`, `fidelity`, `cost`, `code_hash`, `depends_on`, `assumes`, `predictors` | A function that can create evidence. Registered via `@reval.producer`. `predictors` = the model artifacts whose output *is* the quantity (used for independence). |
| `Evidence` | `id`, `producer_id`, `producer_kind`, `fidelity`, `subject_id`, `result` (`quantity`, `unit`, `point`, `interval`, `uncertainty_kind`, `in_domain`, `domain_report`), `deps`, `scope`, `tolerances`, `provenance`, `cost`, `derived_from_evidence`, `waiver` | Immutable once stored. No timestamps: `id` is a pure content hash. |
| `Dependency` | `selector`, `version_hash` | Field-level. A bare `art` selector (written `selector="*"` in prose) means the whole artifact: a coarse, fail-closed default. |
| `Scope` | `box: {variable: [lo, hi]}`, `assumption_ids` | The region and the assumptions under which the evidence is claimed to hold. `assumption_ids` always includes the producer's `assumes` (D9). |
| `Tolerance` | `selector`, `sensitivity` (raw), `input_unit`, `output_unit`, `valid_range`, `safety_factor κ`, `source`, `assumption_id` (required) | A declared bound used for tolerance-aware carry-forward. `source` must say how it was obtained (for example, "finite differences on LPTN v3, grid G2"). |
| `Waiver` | `author`, `justification`, `claim_id`, `requirement_hash` | Attached to `waiver`-kind evidence. Applies to exactly one claim (D10). |
| `Policy` | `id`, `alternatives: [[EvidenceRequirement]]` | Disjunctive normal form: OR over clauses, AND within a clause. |
| `EvidenceRequirement` | `kind`, `min_fidelity`, `in_domain: bool`, `independent_of: [kind]` | One conjunct. |
| `Snapshot` | `id`, `git_rev`, `manifest_hash`, `quantities`, `artifacts`, `versions`, `assumptions`, `requirements`, `subjects`, `claims`, `policies`, `producers` | The project state. `id = content_id(snapshot, exclude={id, git_rev})`. This is the **only** definition (D1). |
| `ChangeSet` | `from_snapshot`, `to_snapshot`, `changes: [Change]` | `Change` = `kind`, `target`, `old`, `new`, `delta`, `groups`, `columns`, `rows_bbox`, `detail`. Kinds are listed in §7. |
| `Assessment` | `claim_id`, `snapshot_id`, `status`, `reasons: [Reason]`, `evidence: [EvidenceUse]`, `satisfied_clause`, `input_hash` | Pure function output. Stored append-only, in numbered batches (D18). |
| `RevalidationPlan` | `id`, `snapshot_id`, `planner`, `objective`, `budget`, `runs: [PlannedRun]`, `total_cost`, `chosen_clauses`, `unrestorable`, `deferred`, `solver_status`, `reproducible` | `unrestorable` = no cover even with an infinite budget. `deferred` = restorable but over budget. |

## 2. Evidence verdicts

Every evidence item is reduced to a three-valued **verdict** against a claim's requirement (shown here for `op = "<="`, limit *L*; `>=` is mirrored).
Pass and fail bounds are **inclusive on the pass side**: `hi ≤ L` passes, `lo > L` fails.

| Producer kind | Interval used | pass | fail | inconclusive |
|---|---|---|---|---|
| `measurement` | measured peak ± sensor uncertainty *u* | ŷ + u ≤ L | ŷ − u > L | otherwise |
| `ml_prediction` | conformal interval [lo, hi] at level 1−α | in domain ∧ hi ≤ L | in domain ∧ lo > L | otherwise, **including every out-of-domain case** and an unbounded quantile (q̂ = ∞) |
| `physics_sim` | ŷ ± model-form band δ (from validation residuals) | ŷ + δ ≤ L | ŷ − δ > L | otherwise |
| `analytic` | exact value or declared bound | value ≤ L | value > L | — |
| `waiver` | — | always pass (only for its own claim), with mandatory justification + author | — | — |

Carried-forward evidence (§4) uses its *inflated* interval. Symmetric inflation can turn PASS into INCONCLUSIVE, but never into FAIL.
The units of the evidence and the requirement must be identical strings, because the manifest loader converts them to canonical units. A mismatch is a programming error.

## 3. Claim status

Status is **history-free** (D4): it depends only on the current snapshot and the evidence items with their freshness classes. Previous assessments are never an input,
so revisiting an old snapshot or making an unrelated change can't flip a status (I1, I2).

Definitions (for one claim):
- **Item**: an evidence item for the claim's subject and quantity, with its freshness class (§4). INVALIDATED items are included. They never support anything, but they drive STALE.
  Waivers count only for their own `claim_id`.
- **Fresh**: class ∈ {FRESH_EXACT, FRESH_OUT_OF_SCOPE, CARRY_FORWARD}. **Eligible**: fresh, and its kind appears in some conjunct of the claim's policy (a matching waiver is always eligible).
- **Recorded verdict**: the verdict of an item's *recorded* (un-inflated) result.
- **Superseded**: an INVALIDATED item for which a fresh item from the same producer exists for the same subject and quantity (it was rerun).

Rules, evaluated in order. The first rule that matches wins:

1. **VIOLATED.** Some eligible item has verdict FAIL. Fail dominates. If an eligible item also passes, the reason `CONFLICTING_EVIDENCE` is added and an engineer must investigate.
2. **WAIVED.** An eligible waiver for this claim exists (`WAIVER_APPLIED`).
3. **STALE (lost fail).** Some non-superseded item of a policy-eligible kind had recorded verdict FAIL and is now INVALIDATED, or was carried forward from FAIL to a non-FAIL verdict.
   A change must never turn a refuted claim into an accepted one without new evidence (I3, I4).
4. **SUPPORTED.** Some policy clause has every conjunct satisfied by distinct, fresh, eligible PASS evidence that meets the clause's `in_domain`, `min_fidelity` and
   `independent_of` constraints (`POLICY_SATISFIED`, `satisfied_clause = k`).
5. **STALE.** Not supported now, but a clause *would* be satisfied if every non-superseded INVALIDATED item, and every carried-forward item, were evaluated at its recorded verdict.
   Support was lost because of a change: through invalidation, or because inflation widened a PASS into INCONCLUSIVE.
6. **INCONCLUSIVE.** Everything else: no evidence (`NO_EVIDENCE`), out of domain (`OUT_OF_DOMAIN`), an interval that straddles the limit (`MARGIN_BELOW_UNCERTAINTY`),
   a missing independent source (`POLICY_UNMET`), and so on.

Only **SUPPORTED** and **WAIVED** count as "accepted". Benchmarks contain no waivers, and WAIVED is excluded from all benchmark metrics.
The `Status` enum's declaration order is **not** the evaluation order. Use the rule list above.

### Default policies (risk-informed, inspired by ASME V&V 40 — not an implementation of it)

Shorthand: `kind{constraints}`. A clause is a list of conjuncts. A policy is a list of clauses.

```
low:    [ml_prediction{in_domain}] | [physics_sim] | [measurement] | [analytic]
medium: [ml_prediction{in_domain}, physics_sim{independent_of: ml_prediction}] | [measurement] | [analytic{min_fidelity: 3}]
high:   [measurement] | [physics_sim{min_fidelity: 2}, ml_prediction{in_domain, independent_of: physics_sim}] | [analytic{min_fidelity: 3}]
```

The manifest uses the structured form (`[{kind: ml_prediction, in_domain: true}, …]`). See `docs/10-interfaces.md` §3.
The analytic clauses exist so that analytic checks (shaft diameter, current limit) can support their claims (D8).

**Independence (D6):** two evidence items are independent iff they have different `producer_kind` **and** the `predictors` of their producers are disjoint.
Independence is about **model form** (which model computed the quantity), not about shared inputs. For example, an ML prediction and an LPTN simulation that both take
inputs from the drive map are independent, because their predictors are `tpm_*` and `lptn`. They may still share training data. `docs/05` §4 states this caveat.

## 4. Freshness and carry-forward

Evidence *e* recorded at snapshot *S*. Moving to snapshot *S′* with change set Δ. `deps*(e)` = the artifacts of e's dependencies plus everything they are transitively
`derived_from`. The algorithm is in [10-interfaces.md](10-interfaces.md) §4.3.

- **Fresh (exact):** every dependency hash is identical in *S′*, the producer code hash is unchanged, no assumption in `e.scope.assumption_ids` (or backing a tolerance) changed,
  the subject didn't change, and there is no `UNKNOWN` change that touches `deps*(e)` (or that can't be located).
- **Relevant changes** are changes that overlap a dependency selector, touch an assumption in scope, change the producer's code, change e's subject, are `UNKNOWN` near e, or
  change an artifact upstream (`derived_from`) of a dependency.
- Each relevant change must be **excused individually**, otherwise *e* is INVALIDATED:
  - **Out of scope:** a row change (`ROWS_ADDED/MODIFIED/REMOVED`) matched through a **column-selector** dependency on a dataset, whose `rows_bbox` (the hull of the old and new rows
    for modifications) is disjoint from `e.scope.box` in at least one variable. Whole-artifact dependencies and upstream (`derived_from`) matches are never excused (D12).
  - **Tolerance:** a numeric `FIELD_CHANGED` with a declared `Tolerance` on exactly that selector, where both the old and new values lie in `valid_range`. It contributes
    `κ · s · |Δf|` to the inflation (κ = `safety_factor`, applied exactly once; `s` = the raw sensitivity, D14).
- **Result:** all excused with zero inflation → FRESH_OUT_OF_SCOPE. All excused with positive inflation → CARRY_FORWARD: the derived item *e′* (interval widened by the total
  inflation, `derived_from_evidence = e.id`) is materialized **for this assessment only** and passed to the status rules *instead of* *e*. It is never stored (D5).
- **Not fresh:** anything else. **`UNKNOWN` changes, missing tolerances, subject changes, upstream changes of derived artifacts, and whole-artifact dependencies on a changed
  artifact always invalidate.** A missing old snapshot also invalidates.

Each tolerance is backed by a required `Assumption` ("sensitivity of peak T_pm to the coolant flow scale ≤ 9 K per unit over 0.7–1.3"),
so a change to the thing that justified the bound invalidates the bound.

## 5. Invariants (each one becomes a property-based test in `tests/property/`)

- **I1 Determinism.** `assess(S)` returns identical assessments and an identical `input_hash` across runs, processes and machines.
- **I2 Locality.** A change to an artifact outside a claim's dependency cone never changes that claim's status. (Status is history-free, so this holds across sequences of snapshots too.)
- **I3 Fail-closed.** Replacing any declared tolerance or scope with "undeclared" never moves a claim *toward* acceptance. This includes a claim whose FAIL evidence would be invalidated (rule 3).
- **I4 No free support.** For a fixed policy and requirement, a change with no new evidence never moves a claim from non-accepted to accepted. This includes losing or widening FAIL
  evidence (rule 3). Loosening a requirement *can* legitimately do this. It is a `REQUIREMENT_CHANGED` and is reported as such.
  **Supersede exception:** a fresh item from the same producer on the same subject and quantity counts as new evidence for the INVALIDATED item it
  supersedes, even when it already existed before the change. Property tests must generate this case explicitly and treat it as new evidence, not as a counterexample.
- **I5 Monotone inflation.** A larger |Δf| never yields a narrower carried-forward interval.
- **I6 Plan soundness.** If every planned run returns a decisive verdict, every claim not listed as `unrestorable` or `deferred` reaches a decided status (Supported, Violated or Waived).
- **I7 Exact-fresh idempotence.** `assess(S)` after `diff(S, S)` equals `assess(S)`.

## 6. Reason codes (`ReasonCode` in `src/reval/domain/status.py`)

| Code | Emitted by | Meaning |
|---|---|---|
| `policy_satisfied` | status rule 4 | A clause is satisfied. The ids of the evidence used are listed. |
| `waiver_applied` | status rule 2 | A waiver for this claim is in effect |
| `conflicting_evidence` | status rule 1 | FAIL and PASS evidence coexist |
| `no_evidence` | rule 6, verdicts | No eligible evidence, or no interval and no point |
| `out_of_domain` | verdicts | ML evidence outside its applicability domain (detail = domain report) |
| `margin_below_uncertainty` | verdicts | The interval straddles the limit, or it is unbounded |
| `policy_unmet` | rule 6 | Some PASS exists but no clause is satisfied (for example, a missing independent source) |
| `evidence_invalidated` | freshness, rules 3 and 5 | Evidence lost freshness. `detail.lost_fail = true` for rule 3. |
| `unknown_change` | freshness | Unclassifiable change, missing producer, or missing old snapshot |
| `missing_tolerance` | freshness | A field changed with no usable tolerance |
| `requirement_changed` | status (informational), waiver freshness | The claim's requirement changed in this diff |

## 7. Change kinds (`ChangeKind`, `10-interfaces.md` §2)

| Kind | Produced when | Target |
|---|---|---|
| `field_changed` / `field_added` / `field_removed` | A yaml-fields pointer leaf differs, appears or disappears | `art#/pointer` |
| `rows_added` / `rows_modified` / `rows_removed` | Dataframe row groups appear, change (`columns` lists which) or disappear | `art[cols]` or `art` |
| `artifact_added` / `artifact_removed` / `artifact_changed` | Artifact entry or file added or removed. Model/file content or dataframe column set changed. | `art` |
| `requirement_changed` / `assumption_changed` / `policy_changed` / `subject_changed` / `claim_changed` | Any field differs. Add/remove uses the same kind with `detail="added"`/`"removed"`. | entity id |
| `producer_code_changed` | Producer `code_hash` or `depends_on` differs | producer id |
| `unknown` | Anything a hasher or the differ can't classify | best-effort selector or free text |

## 8. Manifest sketch (`reval.yaml`)

```yaml
version: 1
project: motor-thermal
quantities: {pm_peak: degC, sw_peak: degC, shaft_d: mm, is_peak: A}

artifacts:
  measures:   {kind: dataset, path: data/processed/measures.parquet, hasher: dataframe, key: [profile_id, t]}
  splits:     {kind: params,  path: splits.yaml}
  drive_map:  {kind: model,   path: models/drive_map.joblib, derived_from: [measures, splits]}
  tpm_ridge:  {kind: model,   path: models/tpm_ridge.joblib, derived_from: [measures, splits]}
  lptn:       {kind: params,  path: params/lptn.yaml, derived_from: [measures, splits]}
  cooling:    {kind: params,  path: params/cooling.yaml}
  shaft:      {kind: params,  path: params/shaft.yaml}

assumptions:
  A-coolant-range: {statement: "Coolant inlet temperature within the tested range", variable: coolant, unit: degC, bounds: [18, 70]}
  A-sensor-pm:     {statement: "Magnet telemetry uncertainty", variable: pm_sensor_uncertainty, unit: K, value: 2.0}
  A-flow-sens:     {statement: "Peak T_pm sensitivity to flow_scale bounded over 0.7-1.3", variable: flow_scale, unit: "1", bounds: [0.7, 1.3]}

requirements:
  R-PM-MAX:  {text: "Magnet temperature shall not exceed the declared limit", quantity: pm_peak, op: "<=", limit: 110, unit: degC, criticality: high}
  R-SW-MAX:  {text: "Stator winding temperature shall not exceed the declared limit", quantity: sw_peak, op: "<=", limit: 130, unit: degC, criticality: medium}
  R-SHAFT-D: {text: "Shaft diameter within tolerance", quantity: shaft_d, op: "<=", limit: 30.05, unit: mm, criticality: low}

subjects:
  DC-07:   {kind: duty_cycle, generator: "motor.cycles:blocks", params: {blocks: [[120, 4000, 600], [60, 2500, 900]], coolant: 45, ambient: 25}}
  SHAFT-1: {kind: design, params: {}}

claims:
  - {id: C-DC07-PM, requirement: R-PM-MAX, subject: DC-07}
  - {id: C-DC07-SW, requirement: R-SW-MAX, subject: DC-07}
  - {id: C-SHAFT,   requirement: R-SHAFT-D, subject: SHAFT-1}

producers: [motor.producers]   # importable modules that register @reval.producer functions
```

(The limits above are placeholders. The study's declared limits are chosen after EDA; see [05-motor-domain.md](05-motor-domain.md).)

## 9. Producer SDK sketch

```python
import reval
from reval.sdk import ProducerOutput, interval_result

@reval.producer(
    kind="ml_prediction",
    quantity="pm_peak",
    cost=1,
    depends_on=["tpm_ridge", "drive_map", "cooling#/flow_scale"],
    predictors=["tpm_ridge"],
    assumes=["A-coolant-range"],
)
def predict_pm_peak_ridge(subject: reval.Subject, ctx: reval.Context) -> ProducerOutput:
    traj = ctx.load("drive_map").to_inputs(...)       # built from subject.params via motor.cycles.blocks
    model = ctx.load("tpm_ridge")
    point, bounds, ad = ...                           # peak prediction, PeakConformal interval (or None), DomainReport
    lo, hi = bounds if bounds is not None else (point, point)
    result = interval_result("pm_peak", "degC", point, lo, hi, uncertainty_kind="conformal",
                             in_domain=ad.inside, domain_report=ad.to_dict())
    return ProducerOutput(results=(result,), scope=reval.Scope(box=...))
```

(When the conformal quantile is unbounded, the producer emits `interval=None` instead. See `10-interfaces.md` §5.)

The registry records the code hash: a hash over every `.py` file in the producer's top-level package plus the function's qualified name (D16), so editing a helper module
such as `motor/lptn.py` invalidates. It also records the declared dependencies, predictors and cost.
`ctx.load` **raises** if code tries to read an artifact it didn't declare as a whole or by columns (D11). This keeps dependency declarations honest
(the dynamic-dependency idea from Ekstazi, enforced at the SDK boundary).

## 10. Persistence (relational sketch)

Document tables: each row has indexed key columns plus `body` (the canonical JSON of the domain object). Tables: `snapshots`, `evidence`,
`assessments(snapshot_id, claim_id, seq)`, `plans`, `jobs`, `reports`. Evidence and assessments are append-only. A re-assessment of the same snapshot writes a new
`seq` batch, and reads return the latest batch. Nothing is updated in place, except `jobs.state`. Carried-forward evidence is never stored. Full column list: `docs/10-interfaces.md` §8.
