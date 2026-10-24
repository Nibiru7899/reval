# 04 — Algorithms

Notation: snapshot *S*. Evidence set *E*. Claims *C*. Producers *P*. Requirement of claim *c* is (*q_c*, ≤, *L_c*). Policy of *c* is
*Π_c* = ⋁_k ⋀_{r ∈ K_{c,k}} r.

## A1. Snapshot hashing (E2 input)

- Each artifact is hashed by a kind-specific hasher that returns a whole-artifact hash and a map `selector → hash`:
  - `yaml-fields`: a canonical JSON serialization per leaf, keyed by JSON pointer (`#/coolant/inlet_temp`).
  - `dataframe`: per-column hashes, plus per-key-group hashes (for example, per `profile_id`), so a diff can say "rows of profile 17 modified in column `coolant`".
  - `model`: the hash of the serialized estimator **plus** the hashes of its `derived_from` inputs and training config (a constructive trace).
  - `file`: SHA-256 of bytes (fallback; selector `*` only).
- Snapshot id = SHA-256 over the sorted `(artifact_id, content_hash)` list and the manifest hash (a Merkle root).
- Hashing large datasets is cached by `(path, size, mtime)` and verified on demand.
- The full snapshot is serialized to the committed `reval.lock.json` (ADR 0005). Diffs between git revisions read the two locks.

## A2. Diff → change set

Compare field-hash maps of *S* and *S′* per artifact:
- An added or removed selector → `FieldAdded`/`FieldRemoved`.
- A changed leaf with numeric old and new values → `FieldChanged(old, new, Δ)`.
- Dataframe key-group hash changes → `RowsAdded`/`RowsModified` with the bounding box of affected rows over the declared scope variables.
- Producer code hash change → `ProducerCodeChanged`.
- Anything a hasher can't classify → `Unknown` (fail-closed).

Complexity: O(total selectors). This is trivial at capstone scale.

## A3. Freshness (E2 core)

```
for e in evidence_reachable_from(changes):           # reverse-reachability in E1 from changed nodes
    status[e] = classify(e, changes ∩ deps*(e))       # deps* = transitive through derived_from
classify:
    if no relevant change                       → FRESH_EXACT
    if every relevant change is Rows* and
       rows_bbox ∩ e.scope.box = ∅ and
       no derived artifact on the path changed  → FRESH_OUT_OF_SCOPE
    if every relevant change is FieldChanged and
       each has Tolerance with Δ in valid_range → CARRY_FORWARD(inflation = Σ κ·s·|Δ|)
    else                                        → INVALIDATED (reason codes per change)
```

Reverse reachability is a NetworkX `descendants` call on the reversed dependency graph. A claim's status is recomputed only
if one of its evidence items changed class (an incremental update).

### Where tolerances come from (motor domain)
Sensitivities *s_f* are estimated by central finite differences on the calibrated LPTN, taking the max of |∂ peak / ∂ f| over a grid
covering `valid_range` and the claim's scope box, then multiplied by the safety factor κ (default 1.5). The grid, the LPTN version,
and κ are recorded in `Tolerance.source`. The estimate is **empirical, not a proof**. That is exactly why RQ2 measures whether
carry-forward ever causes an unsupported acceptance, and why ablation A2 turns it off.

## A4. Applicability domain (E3)

The model's validated envelope is built from the calibration and training data in the model's input-feature space
(EWMA features, standardized):

1. **Range box:** per-feature [q_0.5%, q_99.5%]. Explainable ("coolant 72 °C > envelope max 68.9 °C").
2. **kNN distance:** mean distance to *k* = 10 nearest training points. Threshold τ = the 99th percentile of the same statistic on calibration points (leave-profile-out).
3. A subject trajectory is **in domain** iff every timestep passes both checks. (Strict. A relaxed "≥ 99 % of timesteps" variant is tested in ablation A4.)

The AD report lists the first violating timestep, the violating features, and the distances. That report goes straight into the UI.

## A5. Calibrated intervals for peak temperature (E3)

Claims concern the **peak** of a temperature trajectory over a duty cycle, so calibration is done on peaks:

1. Cut each calibration profile into non-overlapping windows of the duty-cycle length class (short, medium, long).
2. For each window, compute the nonconformity score `r = |peak(ŷ) − peak(y)|`. A normalized variant divides by a local difficulty estimate (CQR in ablation A5).
3. Split-conformal quantile `q̂ = r_(⌈(n+1)(1−α)⌉)` per length class.
4. Interval = [peak(ŷ) − q̂, peak(ŷ) + q̂].

**Caveats that must appear in the report:** windows from the same profile are not exchangeable with each other. Coverage is
therefore verified *empirically* on held-out test profiles (RQ4), not assumed. Under covariate shift (out of domain) the guarantee
doesn't apply, which is why the ML verdict is `inconclusive` outside the domain regardless of the interval.

## A6. Claim status (E3)

Direct evaluation of the rules in [03-domain-model.md §3](03-domain-model.md). Clause satisfaction with "distinct evidence"
and `independent_of` constraints is a tiny bipartite matching problem (conjuncts ↔ evidence). Clauses have ≤ 3 conjuncts, so
brute force is fine. Every rule that fires emits a `Reason(code, evidence_ids, detail)`.

## A7. Revalidation planner (E4)

### Candidate generation
For each non-accepted, non-violated claim *c* and each clause *k* of *Π_c*, and each conjunct *r* not already satisfied by
fresh passing evidence, enumerate the producer runs *j* (producer × subject × settings) that *could* satisfy *r*: matching kind,
fidelity, independence, and availability (for example, `measurement` exists in Tier A only for recorded segments). Existing fresh
evidence enters as pre-selected with cost 0, so **reuse is automatic**.

### Exact formulation (min cost, restore all restorable)

Variables: z_j ∈ {0,1} (run *j*), y_{c,k} ∈ {0,1} (clause *k* chosen for claim *c*), u_c ∈ {0,1} (claim *c* left unrestored).

```
min   Σ_j cost_j · z_j  +  M · Σ_c w_c · u_c
s.t.  Σ_k y_{c,k} + u_c ≥ 1                         ∀ c
      y_{c,k} ≤ Σ_{j ∈ J(c,k,r)} z_j                 ∀ c, k, r ∈ K_{c,k}
      (independence)  for conjuncts r ≠ r′ in the same clause, a single run can't satisfy both
```

w_c = criticality weight (low 1, medium 3, high 10). M is larger than the total cost of all candidates.
One run can serve many claims: one bench measurement of DC-07 yields evidence for both `pm_peak` and `sw_peak`.

### Budgeted variant
`max Σ_c w_c (1 − u_c)` subject to `Σ_j cost_j z_j ≤ B`, using the same constraints. It powers the UI's budget slider.

### Sequential (expected-cost) variant — stretch goal
A planned run may return `inconclusive`. Estimate p_j = P(decisive) from the current interval width relative to the margin.
For a single claim with alternative clauses, ordering clauses by `cost/p` approximates the optimal sequential test order
(the classic sequential-testing and Pandora's-box line of work, Weitzman 1979). Execute → re-assess → re-plan (receding horizon).
Compare expected cost against the one-shot ILP in the benchmark.

### Solver
OR-Tools CP-SAT, with a fixed seed and `num_workers=1` for determinism. Problem sizes are hundreds of variables, so solves take
milliseconds. The problem is NP-hard in general (it contains set cover). The greedy planner (pick the run with the best
weighted-obligations-per-cost ratio, repeat) is the approximation baseline.

## A8. Design optimizer (motor example, not part of the ReVal core)

Maximize delivered mechanical energy of a parameterized duty cycle θ (block torque levels, speeds, durations; fixed total time)
subject to the thermal limits. Three variants:

- **O1** constraint on the point prediction: peak(ŷ(θ)) ≤ L.
- **O2** constraint on the conformal upper bound.
- **O3** O2 plus an applicability-domain constraint, as a penalty on the kNN distance above τ.

Solved with `scipy.optimize.differential_evolution` (seeded). Expected finding, to be tested rather than assumed: O1 drifts
out of domain, and ReVal flags its optimum as Inconclusive. O3's optimum is less aggressive but Supported.
