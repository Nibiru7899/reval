# 04 — Algorithms

Notation: snapshot *S*. Evidence set *E*. Claims *C*. Producers *P*. Requirement of claim *c* is (*q_c*, ≤, *L_c*). Policy of *c* is
*Π_c* = ⋁_k ⋀_{r ∈ K_{c,k}} r.

## A1. Snapshot hashing (E2 input)

- Each artifact is hashed by a kind-specific hasher that returns an own content hash and a map `selector → hash`:
  - `yaml-fields`: a canonical JSON serialization per leaf, keyed by JSON pointer (`#/flow_scale`).
  - `dataframe`: per-column hashes, plus per-key-group hashes (for example, per `profile_id`), so a diff can say "rows of profile 17 modified in column `coolant`".
  - `model`: the hash of the serialized estimator.
  - `file`: SHA-256 of bytes (fallback; whole-artifact selector only).
- **Upstream folding (every hasher, D3):** if the artifact has `derived_from`, its content hash = SHA-256 of its own hash joined with the upstream content hashes
  (a constructive trace). So an upstream change changes every derived artifact's hash, even if it wasn't regenerated. Field hashes stay own-only.
- **Snapshot id (D1):** `Snapshot.id = content_id(snapshot, exclude={"id", "git_rev"})`, the SHA-256 of the canonical JSON of the whole snapshot (manifest entities, versions with
  field hashes/values/row groups, producers with code hashes). `git_rev` is excluded, so the same state at two commits has the same id. This is the only definition
  (`10-interfaces.md` §2).
- Hashing large datasets is cached by `(path, size, mtime)` and verified on demand.
- The full snapshot is serialized to the committed `reval.lock.json` (ADR 0005). Diffs between git revisions read the two locks.

## A2. Diff → change set

Compare field-hash maps of *S* and *S′* per artifact:
- An added or removed pointer → `FIELD_ADDED`/`FIELD_REMOVED`.
- A changed leaf → `FIELD_CHANGED(old, new, Δ)` (Δ only when both are numeric).
- Dataframe key-group hash changes → `ROWS_ADDED`/`ROWS_MODIFIED`/`ROWS_REMOVED`, with `rows_bbox` = the component-wise hull of the affected groups' bounding boxes
  (old **and** new for modifications).
- Manifest entity changes → `REQUIREMENT_/ASSUMPTION_/POLICY_/SUBJECT_/CLAIM_CHANGED`. Producer code hash change → `PRODUCER_CODE_CHANGED`.
- Anything a hasher can't classify → `UNKNOWN` (fail-closed).
Exact rules: `10-interfaces.md` §4.2.

Complexity: O(total selectors). This is trivial at capstone scale.

## A3. Freshness (E2 core)

```
classify(e):
    if producer missing, or (waiver and requirement hash changed)        → INVALIDATED
    if all dep hashes equal, code hash equal, no scoped assumption changed,
       subject unchanged, no UNKNOWN touching deps*(e)                   → FRESH_EXACT
    R = relevant changes  (selector overlap · scoped assumption · producer code ·
                           subject of e · UNKNOWN near e · upstream (derived_from) of a dep)
    for c in R:                                                           # each excused individually
        Rows* via a column-selector dataset dep with rows_bbox ∩ e.scope.box = ∅ in ≥ 1 variable → excused
        FIELD_CHANGED with a Tolerance on c.target, old AND new in valid_range        → excused, inflation += κ·s·|Δ|
        anything else                                                                  → unexcused
    if any unexcused     → INVALIDATED (one reason per unexcused change)
    elif inflation > 0   → CARRY_FORWARD   (e′ = e with interval widened by inflation; used instead of e, never stored)
    else                 → FRESH_OUT_OF_SCOPE
```

The full step list, including relevance rules (a)–(f), is in `10-interfaces.md` §4.3. Whole-artifact deps, subject changes, and upstream changes of derived artifacts are
never excused (fail-closed). Status is recomputed from scratch for every assessment. It is history-free, so no incremental bookkeeping can drift.

### Where tolerances come from (motor domain)
Sensitivities *s_f* are estimated by central finite differences on the calibrated LPTN, taking the **raw** max of |∂ peak / ∂ f| over a grid
covering `valid_range` and the claim's scope box. The safety factor κ (default 1.5) is stored separately in `Tolerance.safety_factor` and applied **once**,
at inflation time (D14). The grid, the LPTN version, and κ are recorded in `Tolerance.source`. Every tolerance names its backing assumption (`assumption_id`, required),
and declares its `input_unit` and `output_unit`. The output unit is the quantity's difference unit (K for °C quantities). The motor example's main tolerated field is
`cooling#/flow_scale`, mapped into the LPTN as `R_ic ∝ flow_scale^-0.8`.
The estimate is **empirical, not a proof**. That is exactly why RQ2 measures whether carry-forward ever causes an unsupported acceptance, and why ablation A2 turns it off.
The tolerances and the physics evidence share the design LPTN's model-form error, which is another reason A2/A7 are primary ablations.

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
2. For each window, compute the nonconformity score `r = |peak(ŷ) − peak(y)|`. A normalized variant divides by a local difficulty estimate (CQR, ablation A8).
3. Split-conformal quantile `q̂ = r_(⌈(n+1)(1−α)⌉)` per length class. **Small n:** if `n < ⌈1/α⌉ − 1`, then `⌈(n+1)(1−α)⌉ > n` and `q̂ = ∞`.
   The producer then emits no interval, and the ML verdict is INCONCLUSIVE (`MARGIN_BELOW_UNCERTAINTY`). Mitigations: merge length classes, or use profile-level
   calibration (one score per profile, the max over its windows).
4. Interval = [peak(ŷ) − q̂, peak(ŷ) + q̂].

**Caveats that must appear in the report:** windows from the same profile are not exchangeable with each other. Coverage is
therefore verified *empirically* on held-out test profiles (RQ4), not assumed. Under covariate shift (out of domain) the guarantee
doesn't apply, which is why the ML verdict is `inconclusive` outside the domain regardless of the interval. Coverage on drive-map (synthetic) subjects
can't be checked in Tier A; it is reported separately from Tier B. The guarantee is marginal, not per claim, so an UAR_truth floor of about α near the limit is expected.

## A6. Claim status (E3)

Direct evaluation of the history-free rules in [03-domain-model.md §3](03-domain-model.md) (VIOLATED → WAIVED → STALE (lost fail) → SUPPORTED → STALE → INCONCLUSIVE).
Clause satisfaction with "distinct evidence" and `independent_of` constraints (different kind and disjoint `predictors`) is a tiny bipartite matching problem
(conjuncts ↔ evidence). Clauses have ≤ 3 conjuncts, so brute force is fine. The STALE rule runs the same matching with non-superseded INVALIDATED items
and CARRY_FORWARD items treated as fresh at their recorded (un-inflated) verdicts. Every status emits at least one `Reason(code, evidence_ids, detail)`: SUPPORTED → `POLICY_SATISFIED`,
WAIVED → `WAIVER_APPLIED`.

## A7. Revalidation planner (E4)

### Candidate generation
For each STALE or INCONCLUSIVE claim *c*, every conjunct *r* of every clause *k* of *Π_c* becomes an obligation (D7). Candidates *j* are:
- **reuse candidates:** each existing fresh PASS evidence item for *c*'s subject, cost 0. Reuse therefore happens inside the same matching, with the same
  distinctness and independence checks;
- **new runs:** producer × subject pairs that are available (for example, `measurement` exists in Tier A only for recorded test segments), that don't already have
  FRESH_EXACT evidence at this snapshot (rerunning a deterministic producer would reproduce it; carried-forward and out-of-scope items stay rerunnable),
  and, for ML producers, that aren't known to be out of domain (regardless of the
  conjunct's `in_domain` flag).
- **lost-fail obligations:** for each non-superseded lost-fail item of *c* (03 §3 rule 3), a mandatory obligation `rerun:<producer>@<subject>` that only the new-run
  candidate of that producer and subject satisfies. Every clause of *c* additionally requires it (`y_{c,k} ≤ x_{j_rerun}` ∀ k), so reusing evidence at cost 0 never
  restores a lost-fail claim. If no such candidate is available, *c* is `unrestorable`.

### Exact formulation (min cost, restore all restorable)

Variables: z_j ∈ {0,1} (run *j* selected), x_{j,o} ∈ {0,1} (run *j* assigned to obligation *o*), y_{c,k} ∈ {0,1} (clause *k* chosen for claim *c*),
u_c ∈ {0,1} (claim *c* left unrestored).

```
min   Σ_j cost_j · z_j  +  M · Σ_c w_c · u_c
s.t.  Σ_k y_{c,k} + u_c ≥ 1                         ∀ c
      y_{c,k} ≤ Σ_j x_{j,o}                          ∀ c, k, o ∈ K_{c,k}
      x_{j,o} ≤ z_j                                  ∀ j, o
      Σ_{o ∈ K_{c,k}} x_{j,o} ≤ 1                    ∀ j, c, k      (one run counts once per clause: distinctness)
      x_{j,o} + x_{j′,o′} ≤ 1                        for o.independent_of ∋ kind(o′) and (predictors(j) ∩ predictors(j′) ≠ ∅ or kind(j) = kind(j′))  (independence)
```

w_c = integer criticality weight (low 1, medium 3, high 10). Costs are scaled to integers (×100). M = 1 + Σ_j cost_j, which is larger than the total cost of all candidates.
One run can serve many claims: one bench measurement of DC-07 yields evidence for both `pm_peak` and `sw_peak`.
`unrestorable` = claims with no coverable clause even if every candidate is selected. `deferred` = restorable claims left uncovered under a budget.

### Budgeted variant
Maximize `Σ_c w_c (1 − u_c)` subject to `Σ_j cost_j z_j ≤ B`, using the same constraints. Ties are broken toward lower cost with a single integer objective
(`10-interfaces.md` §4.6). It powers the UI's budget slider.

### Sequential (expected-cost) variant — stretch goal
A planned run may return `inconclusive`. Estimate p_j = P(decisive) from the current interval width relative to the margin.
For a single claim with alternative clauses, ordering clauses by `cost/p` approximates the optimal sequential test order
(the classic sequential-testing and Pandora's-box line of work, Weitzman 1979). Execute → re-assess → re-plan (receding horizon).
Compare expected cost against the one-shot ILP in the benchmark.

### Solver
OR-Tools CP-SAT, with a fixed seed and `num_workers=1` for determinism. Problem sizes are hundreds of variables, so solves take
milliseconds. A solve that hits the time limit returns `FEASIBLE`. The plan records this and is marked `reproducible=False`, and tests assert `OPTIMAL`. The problem is NP-hard in general (it contains set cover). The greedy planner (pick the run with the best
weighted-obligations-per-cost ratio, repeat) is the approximation baseline.

## A8. Design optimizer (motor example, not part of the ReVal core)

Maximize delivered mechanical energy of a parameterized duty cycle θ (block torque levels, speeds, durations; fixed total time)
subject to the thermal limits. Three variants:

- **O1** constraint on the point prediction: peak(ŷ(θ)) ≤ L.
- **O2** constraint on the conformal upper bound.
- **O3** O2 plus an applicability-domain constraint, as a penalty on the kNN distance above τ.

Solved with `scipy.optimize.differential_evolution` (seeded). Expected finding, to be tested rather than assumed: O1 drifts
out of domain, and ReVal flags its optimum as Inconclusive. O3's optimum is less aggressive but Supported.
