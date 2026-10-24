# 10 — Interfaces (implementation contract)

This is the **exact contract** that implementation tasks code against. Names, module paths, fields, and signatures are binding.
If a task needs to deviate, write the question in `docs/log/questions.md` and stop. Do not improvise semantics.
`docs/03-domain-model.md` defines meaning. This file defines shape.

---

## 1. Conventions

### 1.1 Base model
```python
# src/reval/domain/base.py
from pydantic import BaseModel, ConfigDict

class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=False)
```
Every domain object subclasses `Frozen`. Collections in fields are `tuple[...]` (ordered, immutable) or `dict[str, ...]`
(treated as immutable by convention; never mutate after construction).

### 1.2 Canonical JSON and hashing (pure; lives in core)
```python
# src/reval/core/canonical.py
def canonical_json(obj: object) -> bytes:
    """json.dumps(to_jsonable(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8").
    Pydantic models → model_dump(mode="json"); tuples → lists; floats → repr-stable (use float as-is; NaN/inf raise ValueError)."""

def sha256_hex(data: bytes) -> str: ...                     # lowercase hex, 64 chars
def content_id(obj: object, *, exclude: frozenset[str] = frozenset({"id"})) -> str:
    """sha256_hex(canonical_json(obj without excluded top-level keys))."""
```

### 1.3 Units
- Absolute temperatures are stored in `degC`. Temperature **differences** (margins, interval half-widths, tolerances, inflation) are in `K`.
- Every quantity has one canonical unit, declared in the manifest `quantities:` map. The manifest loader converts requirement limits to it
  with `pint`. After loading, **core never converts units**. It only checks that the strings are equal.
- Length uses `mm`. Current uses `A`. Speed uses `rpm`. Torque uses `N*m`.

### 1.4 Selector syntax (dependency references)
| Form | Meaning | Example |
|---|---|---|
| `art` | Whole artifact (coarse, fail-closed on any change) | `tpm_model` |
| `art#/json/pointer` | One leaf or subtree of a params file (RFC 6901 pointer) | `cooling#/coolant/flow_lpm` |
| `art[col1,col2]` | Columns of a dataset (all row groups) | `measures[pm,coolant]` |

```python
# src/reval/domain/selectors.py
class Selector(Frozen):
    artifact_id: str
    pointer: str | None = None          # "/coolant/flow_lpm"
    columns: tuple[str, ...] = ()       # sorted
    @classmethod
    def parse(cls, text: str) -> "Selector": ...   # raises ManifestError on bad syntax
    def render(self) -> str: ...                   # inverse of parse (canonical form; columns sorted)
    def covers(self, other: "Selector") -> bool:
        """True if same artifact and (self is whole) or (pointer prefix relation either way: '/a' vs '/a/b')
        or (column sets intersect, or either side has no columns)."""
```

### 1.5 Graph node ids
`artifact:<id>`, `field:<selector>`, `assumption:<id>`, `requirement:<id>`, `subject:<id>`, `claim:<id>`, `evidence:<id>`, `producer:<id>`.

### 1.6 Determinism
No `datetime.now`, no `random` in core. Sort every output collection by id. CP-SAT uses `num_workers=1` and `random_seed=0`.

---

## 2. `reval.domain`

```python
# quantities.py
class Interval(Frozen):
    lo: float
    hi: float
    unit: str
    # validator: lo <= hi, both finite
    def widen(self, delta_k: float) -> "Interval": ...   # delta_k >= 0 else ValueError; returns [lo-δ, hi+δ]
    @property
    def width(self) -> float: ...

# artifacts.py
class ArtifactKind(StrEnum): DATASET="dataset"; MODEL="model"; PARAMS="params"; CODE="code"; DOCUMENT="document"

class Artifact(Frozen):
    id: str
    kind: ArtifactKind
    path: str                          # POSIX, relative to project root
    hasher: Literal["file", "yaml-fields", "dataframe", "model"]
    derived_from: tuple[str, ...] = () # artifact ids (constructive trace)
    key: tuple[str, ...] = ()          # dataframe: first element = row-group column (e.g. "profile_id")

class RowGroupInfo(Frozen):
    n_rows: int
    bbox: dict[str, tuple[float, float]]    # numeric column -> (min, max)

class ArtifactVersion(Frozen):
    artifact_id: str
    content_hash: str                       # "missing" if the file doesn't exist
    field_hashes: dict[str, str] = {}       # yaml: "/a/b" -> hash; dataframe: "c=<col>" and "g=<group>/c=<col>" -> hash
    field_values: dict[str, float | int | str | bool | None] = {}   # yaml scalar leaves only, keyed by pointer
    row_groups: dict[str, RowGroupInfo] = {}                        # dataframe only, keyed by str(group value)

# engineering.py
class Assumption(Frozen):
    id: str
    statement: str
    variable: str
    unit: str
    bounds: tuple[float, float] | None = None
    value: float | None = None
    tol: float | None = None
    # validator: exactly one of (bounds) or (value[, tol]) is set

class Criticality(StrEnum): LOW="low"; MEDIUM="medium"; HIGH="high"
class Comparator(StrEnum): LE="<="; GE=">="

class Requirement(Frozen):
    id: str
    text: str
    quantity: str
    op: Comparator
    limit: float                 # canonical unit of `quantity`
    unit: str
    criticality: Criticality

class SubjectKind(StrEnum): DUTY_CYCLE="duty_cycle"; DESIGN="design"; OPERATING_POINT="operating_point"

class Subject(Frozen):
    id: str
    kind: SubjectKind
    generator: str | None = None          # "module:function", e.g. "motor.cycles:blocks"
    params: dict[str, Any] = {}           # JSON-serializable only

class Claim(Frozen):
    id: str
    requirement_id: str
    subject_id: str
    policy_id: str | None = None          # None → requirement.criticality.value

# evidence.py
class ProducerKind(StrEnum):
    ML_PREDICTION="ml_prediction"; PHYSICS_SIM="physics_sim"; MEASUREMENT="measurement"; ANALYTIC="analytic"; WAIVER="waiver"

DEFAULT_FIDELITY = {ML_PREDICTION: 1, PHYSICS_SIM: 2, MEASUREMENT: 3, ANALYTIC: 3, WAIVER: 0}

class Producer(Frozen):
    id: str                               # default: "<module>:<function>"
    kind: ProducerKind
    quantities: tuple[str, ...]
    fidelity: int
    cost: float                           # > 0 (waiver: 0 allowed)
    code_hash: str
    depends_on: tuple[str, ...]           # rendered selectors, sorted
    assumes: tuple[str, ...] = ()         # assumption ids, sorted

class Dependency(Frozen):
    selector: str                         # rendered Selector
    version_hash: str                     # hash of that selector in the snapshot the evidence was produced at (§4.3 selector_hash)

class Scope(Frozen):
    box: dict[str, tuple[float, float]] = {}
    assumption_ids: tuple[str, ...] = ()

class Tolerance(Frozen):
    selector: str                         # must be a pointer selector, e.g. "cooling#/coolant/flow_lpm"
    sensitivity: float                    # >= 0, output unit (K) per input unit
    valid_range: tuple[float, float]      # input values for which the bound holds
    safety_factor: float = 1.5            # κ >= 1
    source: str                           # non-empty: how it was obtained
    assumption_id: str | None = None      # assumption backing the bound

class Provenance(Frozen):
    producer_code_hash: str
    snapshot_id: str
    env: dict[str, str] = {}              # package versions
    seed: int | None = None

class EvidenceResult(Frozen):
    quantity: str
    unit: str
    point: float | None = None
    interval: Interval | None = None
    uncertainty_kind: Literal["conformal", "sensor", "model_form", "exact", "none"] = "none"
    in_domain: bool | None = None         # required (not None) for ML_PREDICTION
    domain_report: dict[str, Any] | None = None

class Waiver(Frozen):
    author: str
    justification: str                    # non-empty

class Evidence(Frozen):
    id: str                               # content_id(self)
    producer_id: str
    producer_kind: ProducerKind
    fidelity: int
    subject_id: str
    result: EvidenceResult
    deps: tuple[Dependency, ...]          # sorted by selector
    scope: Scope = Scope()
    tolerances: tuple[Tolerance, ...] = ()
    provenance: Provenance
    cost: float
    derived_from_evidence: str | None = None   # set on carried-forward evidence
    waiver: Waiver | None = None               # required iff kind == WAIVER

# policies.py
class EvidenceRequirement(Frozen):
    kind: ProducerKind
    min_fidelity: int = 0
    in_domain: bool = False
    independent_of: tuple[ProducerKind, ...] = ()

class Policy(Frozen):
    id: str
    alternatives: tuple[tuple[EvidenceRequirement, ...], ...]   # OR of ANDs; each clause 1..3 conjuncts

DEFAULT_POLICIES: dict[str, Policy]   # "low", "medium", "high" exactly as docs/03 §3

# snapshot.py
class Snapshot(Frozen):
    id: str                               # content_id(self)
    git_rev: str | None = None            # excluded from id: content_id(self, exclude={"id", "git_rev"})
    manifest_hash: str
    quantities: dict[str, str]            # quantity -> canonical unit
    artifacts: dict[str, Artifact]
    versions: dict[str, ArtifactVersion]
    assumptions: dict[str, Assumption]
    requirements: dict[str, Requirement]
    subjects: dict[str, Subject]
    claims: dict[str, Claim]
    policies: dict[str, Policy]           # DEFAULT_POLICIES merged with manifest overrides
    producers: dict[str, Producer]
    def policy_for(self, claim_id: str) -> Policy: ...

# changes.py
class ChangeKind(StrEnum):
    FIELD_CHANGED="field_changed"; FIELD_ADDED="field_added"; FIELD_REMOVED="field_removed"
    ROWS_ADDED="rows_added"; ROWS_MODIFIED="rows_modified"; ROWS_REMOVED="rows_removed"
    ARTIFACT_ADDED="artifact_added"; ARTIFACT_REMOVED="artifact_removed"; ARTIFACT_CHANGED="artifact_changed"
    REQUIREMENT_CHANGED="requirement_changed"; ASSUMPTION_CHANGED="assumption_changed"
    POLICY_CHANGED="policy_changed"; SUBJECT_CHANGED="subject_changed"; CLAIM_CHANGED="claim_changed"
    PRODUCER_CODE_CHANGED="producer_code_changed"; UNKNOWN="unknown"

class Change(Frozen):
    kind: ChangeKind
    target: str                           # rendered selector, or entity id for manifest entities / producers
    old: float | int | str | bool | None = None
    new: float | int | str | bool | None = None
    delta: float | None = None            # new - old when both numeric
    groups: tuple[str, ...] = ()          # dataframe row groups affected
    columns: tuple[str, ...] = ()         # dataframe columns affected
    rows_bbox: dict[str, tuple[float, float]] | None = None   # union bbox of affected groups (new version; old for removals)

class ChangeSet(Frozen):
    from_snapshot: str
    to_snapshot: str
    changes: tuple[Change, ...]           # sorted by (kind, target)

# assessment.py
class Reason(Frozen):
    code: ReasonCode
    message: str
    evidence_ids: tuple[str, ...] = ()
    detail: dict[str, Any] = {}

class EvidenceUse(Frozen):
    evidence_id: str
    verdict: Verdict
    freshness: FreshnessClass
    interval_used: Interval | None = None
    used_in_clause: bool = False

class Assessment(Frozen):
    claim_id: str
    snapshot_id: str
    status: Status
    reasons: tuple[Reason, ...]
    evidence: tuple[EvidenceUse, ...]     # sorted by evidence_id
    satisfied_clause: int | None = None
    input_hash: str

# plan.py
class Obligation(Frozen):
    claim_id: str
    clause_index: int
    conjunct_index: int
    requirement: EvidenceRequirement
    @property
    def key(self) -> str: ...             # f"{claim_id}/{clause_index}/{conjunct_index}"

class CandidateRun(Frozen):
    id: str                               # f"{producer_id}@{subject_id}"
    producer_id: str
    subject_id: str
    cost: float
    satisfies: tuple[str, ...]            # obligation keys, sorted

class PlanningProblem(Frozen):
    snapshot_id: str
    claim_weights: dict[str, float]       # claims needing restoration -> weight (low 1, medium 3, high 10)
    clauses: dict[str, tuple[tuple[str, ...], ...]]   # claim_id -> per clause: obligation keys still open ( () = already satisfied )
    obligations: dict[str, Obligation]
    candidates: tuple[CandidateRun, ...]

class PlannedRun(Frozen):
    candidate_id: str
    producer_id: str
    subject_id: str
    cost: float
    discharges: tuple[str, ...]           # obligation keys used by the chosen clauses

class RevalidationPlan(Frozen):
    id: str                               # content_id(self)
    snapshot_id: str
    planner: Literal["ilp", "greedy", "all"]
    objective: Literal["min_cost", "max_restored"]
    budget: float | None = None
    runs: tuple[PlannedRun, ...]          # sorted by (cost, candidate_id)
    total_cost: float
    chosen_clauses: dict[str, int]
    unrestorable: tuple[str, ...]
    solver_status: str                    # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "GREEDY" | "ALL"
```
`reval.domain.__init__` re-exports all public classes above.

---

## 3. `reval.manifest`

### 3.1 YAML schema (`reval.yaml`)
```yaml
version: 1                       # required, must be 1
project: motor-thermal
quantities: {pm_peak: degC, sw_peak: degC, shaft_d: mm, is_peak: A}
artifacts:   {<id>: {kind, path, hasher?, derived_from?, key?}}       # hasher default: params→yaml-fields, dataset→dataframe, model→model, else file
assumptions: {<id>: {statement, variable, unit, bounds? | value? tol?}}
requirements:{<id>: {text, quantity, op, limit, unit, criticality}}
subjects:    {<id>: {kind, generator?, params?}}
claims:      [{id, requirement, subject, policy?}]
policies:                       # optional; overrides/extends DEFAULT_POLICIES by id
  medium:
    - [{kind: ml_prediction, in_domain: true}, {kind: physics_sim, independent_of: [ml_prediction]}]
    - [{kind: measurement}]
producers: [motor.producers]    # importable modules; project root is prepended to sys.path
```

```python
# src/reval/manifest/schema.py — pydantic models mirroring the YAML 1:1 (extra="forbid")
class ManifestModel(BaseModel): ...

# src/reval/manifest/loader.py
def load_manifest(path: Path) -> ManifestModel: ...
    # raises ManifestError(path, message, location) on YAML/schema errors, unknown references
    # (claim → missing requirement/subject/policy, derived_from → missing artifact), cycles in derived_from,
    # or units not convertible to the quantity's canonical unit.
def manifest_hash(path: Path) -> str: ...      # sha256 of canonical_json(parsed YAML)

# src/reval/manifest/snapshot_builder.py
def build_snapshot(project_root: Path, manifest: ManifestModel, registry: "ProducerRegistry",
                   *, git_rev: str | None = None) -> Snapshot: ...
    # converts units (pint), hashes artifacts in topological order of derived_from (§6),
    # collects Producer metadata from the registry, merges policies, computes Snapshot.id.
```

---

## 4. `reval.core` (pure)

### 4.1 `graph.py`
```python
class EvidenceGraph:
    @classmethod
    def build(cls, snapshot: Snapshot, evidence: Sequence[Evidence]) -> "EvidenceGraph": ...
    # Edges (dependency → dependent): artifact→field (one per dep selector), field→evidence, assumption→evidence,
    # producer→evidence, artifact(derived_from src)→artifact(derived), evidence→claim (same subject_id and
    # result.quantity == requirement.quantity), requirement→claim, subject→claim.
    def claim_cone(self, claim_id: str) -> frozenset[str]: ...         # ancestor node ids
    def influence(self, node_id: str) -> frozenset[str]: ...           # descendant node ids
    def evidence_for_claim(self, claim_id: str) -> tuple[Evidence, ...]: ...   # sorted by id
    def to_json(self, focus: str | None = None) -> dict[str, Any]: ...  # {"nodes":[{id,type,label}], "edges":[{source,target,type}]}
```

### 4.2 `diff.py`
```python
def diff_snapshots(old: Snapshot, new: Snapshot) -> ChangeSet: ...
```
Rules:
1. An artifact only in new → `ARTIFACT_ADDED`. Only in old → `ARTIFACT_REMOVED`. A `content_hash` change to/from `"missing"` → `ARTIFACT_REMOVED`/`ARTIFACT_ADDED`.
2. yaml-fields: per pointer, added → `FIELD_ADDED`, removed → `FIELD_REMOVED`, hash differs → `FIELD_CHANGED` (`old`, `new`, and `delta` if both numeric and not bool).
3. dataframe: a group only in new → `ROWS_ADDED`. Only in old → `ROWS_REMOVED`. A group whose `g=<g>/c=<col>` hashes differ → `ROWS_MODIFIED`, `columns` = differing columns.
   Emit **one change per kind per artifact**: `groups` sorted, `columns` = union, `rows_bbox` = union of bboxes of those groups.
   A column-set change (column added or removed) → `ARTIFACT_CHANGED`.
4. model / file: content hash differs → `ARTIFACT_CHANGED`.
5. Manifest entities: any field difference → `REQUIREMENT_/ASSUMPTION_/POLICY_/SUBJECT_/CLAIM_CHANGED` (target = entity id, including add/remove). For a requirement limit change, set old/new/delta.
6. Producer `code_hash` or `depends_on` differs → `PRODUCER_CODE_CHANGED` (target = producer id).
7. Anything not classifiable → `UNKNOWN`.

### 4.3 `freshness.py`
```python
@dataclass(frozen=True)
class FreshnessResult:
    evidence_id: str
    cls: FreshnessClass
    reasons: tuple[Reason, ...]
    inflation_k: float                  # 0.0 unless CARRY_FORWARD
    relevant_changes: tuple[Change, ...]

def selector_hash(snapshot: Snapshot, selector: str) -> str: ...
    # whole → version.content_hash; pointer → sha256 over sorted (k, h) of field_hashes with k == pointer or k.startswith(pointer + "/");
    # columns → sha256 over sorted "c=<col>" hashes; missing artifact → "missing".
def classify_evidence(e: Evidence, old: Snapshot, new: Snapshot, changes: ChangeSet) -> FreshnessResult: ...
def classify_all(evidence: Sequence[Evidence], snapshots: Mapping[str, Snapshot], new: Snapshot,
                 changesets: Mapping[str, ChangeSet]) -> dict[str, FreshnessResult]: ...
    # keyed by evidence id; snapshots/changesets keyed by evidence.provenance.snapshot_id.
    # If the old snapshot is missing → INVALIDATED with UNKNOWN_CHANGE (fail-closed).
def carry_forward(e: Evidence, fr: FreshnessResult, new_snapshot_id: str) -> Evidence: ...
    # requires fr.cls == CARRY_FORWARD and e.result.interval; returns new Evidence with interval.widen(fr.inflation_k),
    # derived_from_evidence=e.id, provenance.snapshot_id=new_snapshot_id, deps re-hashed against new snapshot, id recomputed.
```
**Algorithm for `classify_evidence` (in order):**
1. **Exact shortcut:** if every `dep.version_hash == selector_hash(new, dep.selector)`, `new.producers[e.producer_id].code_hash == e.provenance.producer_code_hash`,
   and no `ASSUMPTION_CHANGED` targets an id in `e.scope.assumption_ids` or a tolerance's `assumption_id` → `FRESH_EXACT`.
   (A missing producer in new → INVALIDATED, `UNKNOWN_CHANGE`.)
2. **Relevance:** change *c* is relevant iff any of these hold:
   (a) `Selector.parse(c.target).covers(Selector.parse(dep.selector))` for some dep. For row changes, columns must intersect when both sides list columns.
   (b) `c.kind == ASSUMPTION_CHANGED` and `c.target` ∈ scope.assumption_ids ∪ {tol.assumption_id}.
   (c) `c.kind == PRODUCER_CODE_CHANGED` and `c.target == e.producer_id`.
   (d) `c.kind in {UNKNOWN}` (always relevant).
   REQUIREMENT/POLICY/SUBJECT/CLAIM changes are **not** relevant to evidence freshness. Status re-evaluation handles them.
3. **Excuse each relevant change** (all must be excused, else INVALIDATED):
   - `ROWS_ADDED/MODIFIED/REMOVED` is excused iff `rows_bbox` is not None and there is ≥ 1 variable *v* in both `rows_bbox` and `scope.box`
     whose intervals are disjoint, **and** the dep it matched is a dataset dep (not via a derived model, since a model's hash changes on its own).
   - `FIELD_CHANGED` with numeric `delta` is excused iff a tolerance has `tol.selector == c.target`, with both `old` and `new` inside `tol.valid_range`.
     It contributes `tol.safety_factor * tol.sensitivity * abs(delta)` to inflation.
   - Every other kind (`UNKNOWN`, `ARTIFACT_*`, `FIELD_ADDED/REMOVED`, `ASSUMPTION_CHANGED`, `PRODUCER_CODE_CHANGED`, a field change with no tolerance) → not excused.
4. Result: there are unexcused changes → `INVALIDATED`. Reasons, one per unexcused change: `UNKNOWN_CHANGE` for UNKNOWN, `MISSING_TOLERANCE` for an untolerated field change, otherwise `EVIDENCE_INVALIDATED`.
   All excused and inflation > 0 → `CARRY_FORWARD`. All excused and inflation == 0 → `FRESH_OUT_OF_SCOPE`.
   A `CARRY_FORWARD` with `e.result.interval is None` → `INVALIDATED` (`MISSING_TOLERANCE`).

### 4.4 `verdicts.py`
```python
def verdict(e: Evidence, req: Requirement) -> tuple[Verdict, tuple[Reason, ...]]: ...
```
- Units: `e.result.unit != req.unit` or `e.result.quantity != req.quantity` → `ValueError` (programming error).
- `WAIVER` → PASS.
- `ML_PREDICTION` with `in_domain is not True` → INCONCLUSIVE + `OUT_OF_DOMAIN` (detail = domain_report).
- Interval `[lo, hi]` = `result.interval`, or `[point, point]` when `uncertainty_kind == "exact"`. Neither available → INCONCLUSIVE + `NO_EVIDENCE`.
- `LE`: `hi <= L` → PASS. `lo > L` → FAIL. Else INCONCLUSIVE + `MARGIN_BELOW_UNCERTAINTY`.
- `GE`: `lo >= L` → PASS. `hi < L` → FAIL. Else INCONCLUSIVE + `MARGIN_BELOW_UNCERTAINTY`.

### 4.5 `status.py`
```python
def assess_claim(claim: Claim, snapshot: Snapshot, evidence: Sequence[tuple[Evidence, FreshnessClass]],
                 previous: Assessment | None, changes: ChangeSet | None = None) -> Assessment: ...
def assess_all(snapshot: Snapshot, evidence: Sequence[tuple[Evidence, FreshnessClass]],
               previous: Mapping[str, Assessment], changes: ChangeSet | None = None) -> dict[str, Assessment]: ...
```
- `evidence` passed in is already post-carry-forward (carried items have class `CARRY_FORWARD`). Only evidence for the claim's subject and quantity is considered.
- **Fresh** = class ∈ {FRESH_EXACT, FRESH_OUT_OF_SCOPE, CARRY_FORWARD}. **Eligible** = fresh and `kind` appears in some conjunct of the policy (waivers always eligible).
- Order (first match wins): VIOLATED (any eligible FAIL; add `CONFLICTING_EVIDENCE` if any eligible PASS too) → WAIVED → SUPPORTED → STALE → INCONCLUSIVE.
- **Clause matching:** for clause *k*, the candidates per conjunct are eligible PASS evidence with matching kind, `fidelity >= min_fidelity`, and `in_domain is True` if required.
  Try `itertools.product` over the candidate lists in id order. The assignment must use distinct evidence. For each conjunct with `independent_of`,
  its evidence must be independent (docs/03 §3) of every assigned evidence whose kind is listed. The first valid assignment (lowest clause index, then
  lexicographic ids) wins. `satisfied_clause = k`. Mark those uses `used_in_clause=True`.
- **STALE:** `previous.status in {SUPPORTED, WAIVED}` and some `previous.evidence` item with `used_in_clause` is now not fresh (its class is INVALIDATED or it's absent).
  Reason `EVIDENCE_INVALIDATED` lists those ids.
- **INCONCLUSIVE reasons:** `NO_EVIDENCE` if there's no eligible evidence. Otherwise the union of the verdict reasons, plus `POLICY_UNMET` if some PASS exists but no clause is satisfied.
- If `changes` contains `REQUIREMENT_CHANGED` for the claim's requirement, add `REQUIREMENT_CHANGED` (informational) to the reasons.
- `input_hash = sha256_hex(canonical_json({claim, requirement, policy, evidence: [(id, class, interval)], previous_status}))`.

### 4.6 `planner.py`
```python
CRITICALITY_WEIGHT = {"low": 1.0, "medium": 3.0, "high": 10.0}

def build_problem(snapshot: Snapshot, assessments: Mapping[str, Assessment],
                  fresh_evidence: Sequence[tuple[Evidence, FreshnessClass]], *,
                  available: Callable[[str, str], bool],            # (producer_id, subject_id) -> runnable?
                  known_out_of_domain: frozenset[tuple[str, str]] = frozenset()) -> PlanningProblem: ...
def plan(problem: PlanningProblem, *, planner: Literal["ilp", "greedy", "all"] = "ilp",
         objective: Literal["min_cost", "max_restored"] = "min_cost", budget: float | None = None) -> RevalidationPlan: ...
```
- Claims to restore: status ∈ {STALE, INCONCLUSIVE}. For each clause, conjuncts already satisfiable by existing fresh PASS evidence are dropped.
  A clause whose open list is empty means the claim is already restorable at no cost.
- A candidate `(producer P, subject S)` is generated when `available(P.id, S.id)` holds. It satisfies obligation *o* iff `o.claim.subject_id == S`, the requirement quantity ∈ `P.quantities`,
  `P.kind == o.requirement.kind`, `P.fidelity >= min_fidelity`, and not (`o.requirement.in_domain` and `(P.id, S) in known_out_of_domain`).
- **ILP (CP-SAT):** integer costs `round(cost * 100)`. Variables `z_j`, `y_{c,k}`, `u_c` as in docs/04 A7. Independence: within a clause, one run can't be counted
  for two conjuncts (add `x_{j,o}` assignment variables with `Σ_o∈clause x_{j,o} ≤ 1`, `x_{j,o} ≤ z_j`, `y_{c,k} ≤ Σ_j x_{j,o}`).
  `M = 1 + Σ cost_int`. `max_restored`: maximize `Σ w_c (1 - u_c)` (weights ×1000 as int), subject to `Σ cost_int z_j ≤ round(budget*100)`. Tie-break by also minimizing cost (lexicographic: solve twice, or a weighted objective with the cost scaled below the smallest weight).
  Solver params: `num_workers=1`, `random_seed=0`, `max_time_in_seconds=10`.
- **greedy:** repeat, picking the candidate with the max `(Σ weights of claims whose cheapest open clause loses an obligation) / cost` (ties → candidate id),
  until every claim has a fully covered clause or nothing improves. Then drop redundant runs in descending cost order.
- **all:** select every candidate that satisfies ≥ 1 obligation.
- `unrestorable` = claims with no fully covered clause after solving.

---

## 5. `reval.uq` (numpy/scipy helpers for producers; pure)

```python
# conformal.py
def conformal_quantile(scores: np.ndarray, alpha: float) -> float: ...
    # n = len(scores); k = ceil((n + 1) * (1 - alpha)); return inf if k > n else sorted(scores)[k - 1]
class SplitConformal:
    def __init__(self, alpha: float) -> None: ...
    def fit(self, y_true: np.ndarray, y_pred: np.ndarray) -> "SplitConformal": ...   # scores = |y_true - y_pred|
    def interval(self, y_pred: float) -> tuple[float, float]: ...
    @property
    def q(self) -> float: ...
def empirical_coverage(y_true: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float: ...

# domain.py
class DomainReport(Frozen):
    inside: bool
    first_violation: int | None           # timestep index
    violating_features: tuple[str, ...]
    max_distance: float
    threshold: float
    frac_outside: float
class ApplicabilityDomain:
    def __init__(self, feature_names: Sequence[str], k: int = 10,
                 box_quantiles: tuple[float, float] = (0.005, 0.995), dist_quantile: float = 0.99) -> None: ...
    def fit(self, X_train: np.ndarray, X_calib: np.ndarray) -> "ApplicabilityDomain": ...   # standardize on train; cKDTree; τ from calib
    def check(self, X: np.ndarray, *, min_inside_frac: float = 1.0) -> DomainReport: ...
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "ApplicabilityDomain": ...
```

---

## 6. `reval.hashing` (adapter, does I/O)

```python
class Hasher(Protocol):
    def __call__(self, artifact: Artifact, root: Path, upstream: Mapping[str, ArtifactVersion]) -> ArtifactVersion: ...
HASHERS: dict[str, Hasher]   # "file", "yaml-fields", "dataframe", "model"
def hash_artifact(artifact: Artifact, root: Path, upstream: Mapping[str, ArtifactVersion]) -> ArtifactVersion: ...
```
- **file:** sha256 of the bytes. No fields.
- **yaml-fields:** `yaml.safe_load`. Flatten to RFC 6901 pointers (lists use indices). `field_hashes[ptr] = sha256(canonical_json(leaf))`. Scalar leaves go into `field_values`.
  `content_hash = sha256(canonical_json(doc))`.
- **dataframe:** lazy-import pandas (raise `MissingExtraError("motor")` if absent). Reads `.parquet` or `.csv`. Group column = `artifact.key[0]` (required).
  For each group *g* (stringified) and column *c*: `sha256(pd.util.hash_pandas_object(col_values, index=False).values.tobytes())` → `g=<g>/c=<c>`.
  `c=<c>` = sha256 over the concatenated group hashes in sorted group order. `row_groups[g]` has `n_rows` and a bbox over numeric columns.
  `content_hash` = sha256 over the sorted `field_hashes` items.
- **model:** `content_hash = sha256(file_sha + "|" + "|".join(upstream[a].content_hash for a in sorted(derived_from)))`. No fields.
  So an upstream change changes the model's hash even if it wasn't retrained (constructive trace; fail-closed).
- Missing file → `ArtifactVersion(content_hash="missing")`.
- Optional cache `.reval/hash-cache.json` keyed by `(path, size, mtime_ns, hasher)` → cached `ArtifactVersion` (task P2-04 may defer it).

---

## 7. `reval.sdk`

```python
def producer(*, kind: ProducerKind | str, quantity: str | Sequence[str], cost: float, fidelity: int | None = None,
             depends_on: Sequence[str] = (), assumes: Sequence[str] = (),
             available_for: Callable[[Subject], bool] | None = None, id: str | None = None,
             registry: "ProducerRegistry | None" = None) -> Callable[[ProducerFn], ProducerFn]: ...
ProducerFn = Callable[[Subject, "Context"], "ProducerOutput"]

class RegisteredProducer(NamedTuple):
    meta: Producer
    fn: ProducerFn
    available_for: Callable[[Subject], bool] | None

class ProducerRegistry:
    def register(self, rp: RegisteredProducer) -> None: ...   # duplicate id → ValueError
    def get(self, producer_id: str) -> RegisteredProducer: ...
    def all(self) -> tuple[RegisteredProducer, ...]: ...      # sorted by id
    def load_modules(self, modules: Sequence[str], project_root: Path) -> None: ...   # sys.path insert + importlib
DEFAULT_REGISTRY: ProducerRegistry

def code_hash(fn: Callable[..., Any]) -> str: ...   # sha256(module source file bytes + b"\n" + qualname.encode())

class Context:
    def __init__(self, project_root: Path, snapshot: Snapshot, producer: Producer) -> None: ...
    def load(self, artifact_id: str) -> Any: ...
        # declared iff some depends_on selector has this artifact_id; else raise UndeclaredDependencyError.
        # .joblib/.pkl → joblib.load; .yaml/.yml → yaml.safe_load; .parquet → pandas.read_parquet; .csv → pandas.read_csv; else bytes.
    def param(self, selector: str) -> Any: ...     # pointer value from a params artifact; selector must be covered by a declared dep
    def assumption(self, assumption_id: str) -> Assumption: ...   # must be in `assumes`
    @property
    def seed(self) -> int: ...                     # deterministic: int(sha256(producer.id + snapshot.id)[:8], 16)

class ProducerOutput(Frozen):
    results: tuple[EvidenceResult, ...]
    scope: Scope = Scope()
    tolerances: tuple[Tolerance, ...] = ()
    waiver: Waiver | None = None

# helpers
def interval_result(quantity: str, unit: str, point: float, lo: float, hi: float, *,
                    uncertainty_kind: str, in_domain: bool | None = None, domain_report: dict[str, Any] | None = None) -> EvidenceResult: ...
def exact_result(quantity: str, unit: str, value: float) -> EvidenceResult: ...

# runner.py
def run_producer(registry: ProducerRegistry, producer_id: str, subject: Subject, snapshot: Snapshot,
                 project_root: Path) -> tuple[Evidence, ...]: ...
    # calls fn; one Evidence per result. deps = [Dependency(sel, selector_hash(snapshot, sel)) for sel in depends_on];
    # provenance(producer_code_hash, snapshot.id, env=installed versions of reval/numpy/scipy/sklearn/pandas if present, seed=ctx.seed);
    # cost = producer cost; id = content_id. Rejects results whose quantity isn't in producer.quantities (ProducerError).
```

---

## 8. `reval.store`

```python
class Store(Protocol):
    def put_snapshot(self, s: Snapshot) -> None: ...            # idempotent on id
    def get_snapshot(self, snapshot_id: str) -> Snapshot | None: ...
    def list_snapshots(self) -> tuple[Snapshot, ...]: ...      # by created_seq ascending
    def put_evidence(self, e: Evidence) -> None: ...            # idempotent on id; never updates
    def list_evidence(self, *, subject_id: str | None = None) -> tuple[Evidence, ...]: ...
    def put_assessments(self, snapshot_id: str, items: Sequence[Assessment]) -> None: ...
    def get_assessments(self, snapshot_id: str) -> dict[str, Assessment]: ...
    def latest_assessed_snapshot(self, *, before: str | None = None) -> str | None: ...
    def put_plan(self, p: RevalidationPlan) -> None: ...
    def get_plan(self, plan_id: str) -> RevalidationPlan | None: ...
    def latest_plan(self, snapshot_id: str) -> RevalidationPlan | None: ...

class SqlStore(Store):
    def __init__(self, url: str) -> None: ...                  # metadata.create_all(engine) for now; Alembic added in P6
def open_store(project_root: Path) -> SqlStore: ...
    # url = env REVAL_DATABASE_URL or f"sqlite:///{project_root/'.reval'/'reval.db'}" (mkdir .reval)
```
Tables (SQLAlchemy Core or ORM, module `store/tables.py`):
`snapshots(id PK, git_rev, created_seq INT autoinc unique, body TEXT)`, `evidence(id PK, subject_id IDX, producer_id IDX, snapshot_id IDX, created_seq, body)`,
`assessments(snapshot_id, claim_id, status, input_hash, body, PK(snapshot_id, claim_id))`, `plans(id PK, snapshot_id IDX, created_seq, body)`,
`jobs(id PK, kind, state, payload, result, created_seq)`, `reports(id PK, snapshot_id, body)`. `body` = `canonical_json(obj).decode()`. Read back with `Model.model_validate_json`.

---

## 9. `reval.gitio`

```python
LOCK_FILE = "reval.lock.json"
def write_lock(project_root: Path, snapshot: Snapshot) -> Path: ...
    # json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=False) + "\n"; LF newlines
def read_lock(path: Path) -> Snapshot: ...
def read_file_at_rev(repo_root: Path, rev: str, rel_path: str) -> bytes: ...
    # subprocess ["git", "-C", repo_root, "show", f"{rev}:{rel_path}"]; nonzero → GitError (message includes stderr)
def snapshot_at_rev(repo_root: Path, rev: str, project_subdir: str = ".") -> Snapshot: ...   # parses the lock at rev; sets git_rev = resolved sha
def resolve_rev(repo_root: Path, rev: str) -> str: ...      # git rev-parse
```

---

## 10. `reval.services`

```python
@dataclass(frozen=True)
class DiffReport:
    changes: ChangeSet
    freshness: dict[str, FreshnessResult]
    before: dict[str, Assessment]
    after: dict[str, Assessment]
    affected_claims: tuple[str, ...]     # status changed or any used evidence not FRESH_EXACT

class Project:
    @classmethod
    def open(cls, root: Path) -> "Project": ...     # loads manifest, registry (load_modules), store
    def snapshot(self, *, write_lock: bool = False) -> Snapshot: ...   # live; stores it
    def assess(self, snapshot: Snapshot | None = None) -> dict[str, Assessment]: ...
    def diff(self, a: Snapshot, b: Snapshot) -> DiffReport: ...
    def plan(self, snapshot: Snapshot | None = None, *, planner: str = "ilp", objective: str = "min_cost",
             budget: float | None = None) -> RevalidationPlan: ...
    def run_plan(self, plan: RevalidationPlan) -> tuple[Evidence, ...]: ...   # runs, stores evidence, re-assesses
    def run(self, producer_id: str, subject_id: str) -> tuple[Evidence, ...]: ...
```
`assess` steps: (1) store the snapshot. (2) Load all evidence. (3) Group it by `provenance.snapshot_id`. Get each old snapshot from the store. A missing old snapshot → INVALIDATED (`UNKNOWN_CHANGE`).
(4) Compute `diff_snapshots(old, current)` once per group. (5) `classify_all`. (6) Apply `carry_forward` to CARRY_FORWARD items. (7) `previous` = the assessments of
`store.latest_assessed_snapshot(before=current.id)` (for `diff(a, b)`: the assessments at `a`, computed if missing). (8) `assess_all`. (9) Store the assessments.
`available(P, S)` = `registry.get(P).available_for(subject)` if set, else True. `known_out_of_domain` = (producer, subject) pairs whose latest fresh ML evidence has `in_domain is False`.

---

## 11. CLI

Commands, options, and exit codes are exactly as in `docs/09-api-and-ui.md` (`init, snapshot [--write|--check], status, diff, plan, run, explain, report, graph, serve, version`).
`--project PATH` (default: cwd) on every command. Output: Rich tables for humans, `--format json` emits `canonical_json` of the result.

---

## 12. Motor example (`examples/motor_thermal/motor/`)

`pytest` config adds `pythonpath = ["src", "examples/motor_thermal"]`. Tests that need the real dataset are marked `@pytest.mark.data` and skip if `data/processed/measures.parquet` is absent.

```python
# data.py
EXPECTED_COLUMNS: tuple[str, ...]   # u_q u_d i_q i_d motor_speed torque coolant ambient stator_winding stator_tooth stator_yoke pm profile_id
def load_raw(path: Path) -> pd.DataFrame: ...                   # validates the schema → SchemaError
def prepare(raw_csv: Path, out_parquet: Path) -> None: ...      # adds t (sample index per profile), sorts by (profile_id, t)
# splits.py
def load_splits(path: Path) -> dict[str, tuple[int, ...]]: ...  # keys train/calib/test/reserve; disjointness asserted
def select(df: pd.DataFrame, profiles: Sequence[int]) -> pd.DataFrame: ...
# features.py
DERIVED = ("i_s", "u_s", "p_el", "is_omega")
EWMA_SPANS: tuple[int, ...]                                      # in samples (2 Hz), from config
def add_derived(df: pd.DataFrame) -> pd.DataFrame: ...
def add_ewma(df: pd.DataFrame, cols: Sequence[str], spans: Sequence[int]) -> pd.DataFrame: ...   # per profile, adjust=False
def feature_matrix(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]: ...
# models.py
class PeakModel:                      # wraps an sklearn regressor for one target + conformal + AD
    target: str
    def fit(self, train: pd.DataFrame, calib: pd.DataFrame, *, window_s: int, alpha: float) -> "PeakModel": ...
    def predict_trajectory(self, traj: pd.DataFrame) -> np.ndarray: ...
    def predict_peak_interval(self, traj: pd.DataFrame) -> tuple[float, float, float]: ...  # (point, lo, hi)
    def domain_check(self, traj: pd.DataFrame) -> DomainReport: ...
def train_all(config: Path) -> None: ...          # writes models/*.joblib + metrics json
# lptn.py
@dataclass(frozen=True)
class LPTNParams: ...                             # C (4), R pairwise, R to coolant, loss coefficients
def simulate(params: LPTNParams, inputs: pd.DataFrame, theta0: np.ndarray, dt: float = 0.5) -> np.ndarray: ...  # (T, 4): pm, sy, st, sw
def identify(train: pd.DataFrame, init: LPTNParams) -> LPTNParams: ...
def model_form_band(params: LPTNParams, test: pd.DataFrame, window_s: int) -> dict[str, float]: ...
# drive_map.py
class DriveMap:
    def fit(self, train: pd.DataFrame) -> "DriveMap": ...
    def to_trajectory(self, subject_params: Mapping[str, Any]) -> pd.DataFrame: ...   # 2 Hz rows with model inputs
    def domain_check(self, subject_params: Mapping[str, Any]) -> DomainReport: ...
# cycles.py
def blocks(params: Mapping[str, Any]) -> pd.DataFrame: ...        # [[torque, speed, duration_s], ...], coolant, ambient → engineer-level trajectory
def recorded(params: Mapping[str, Any], df: pd.DataFrame) -> pd.DataFrame: ...   # {profile_id, start, end}
# optimizer.py
def optimize(variant: Literal["O1", "O2", "O3"], models: Mapping[str, PeakModel], limits: Mapping[str, float], *, seed: int) -> dict[str, Any]: ...
# producers.py — registered with @reval.producer: predict_pm_peak, predict_sw_peak, lptn_sim, bench_measure, shaft_check, current_limit_check
# sensitivities.py
def estimate_tolerances(params: LPTNParams, field: str, grid: Sequence[float], cycles: Sequence[Mapping[str, Any]], kappa: float = 1.5) -> list[Tolerance]: ...
```

---

## 13. Errors (`reval/errors.py`)

```python
class RevalError(Exception): ...
class ManifestError(RevalError): ...            # path, message, location
class UndeclaredDependencyError(RevalError): ...
class ProducerError(RevalError): ...
class MissingExtraError(RevalError): ...        # message: pip install "reval[<extra>]"
class GitError(RevalError): ...
class StoreError(RevalError): ...
class SchemaError(RevalError): ...              # motor data schema mismatch
```
CLI maps `RevalError` → exit code 3 with a one-line message. Anything else is a bug (traceback).

---

**Required follow-ups (outside this file):** move `sqlalchemy>=2.0` from the `server` extra into the main `dependencies` (the CLI store needs it), keeping `alembic` in `server`;
add `rich` to the main dependencies for CLI tables; add `pythonpath = ["src", "examples/motor_thermal"]` and the `data` marker to `[tool.pytest.ini_options]`.
