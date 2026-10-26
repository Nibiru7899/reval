# 10 — Interfaces (implementation contract)

This is the **exact contract** that implementation tasks code against. Names, module paths, fields, and signatures are binding.
If a task needs to deviate, write the question in `docs/log/questions.md` and stop. Do not improvise semantics.
`docs/03-domain-model.md` defines meaning. This file defines shape. Audit rulings that shaped this file: `docs/log/2026-10-26-audit-decisions.md` (D1–D27).

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
- The **difference unit** of a quantity is `K` when its canonical unit is `degC`, and otherwise the canonical unit itself (`mm`, `A`, …).
  `difference_unit(unit: str) -> str` lives in `core/canonical.py`.
- Every quantity has one canonical unit, declared in the manifest `quantities:` map. The manifest loader converts requirement limits to it
  with `pint`. After loading, **core never converts units**. It only checks that the strings are equal.
- Length uses `mm`. Current uses `A`. Speed uses `rpm`. Torque uses `N*m`.

### 1.4 Selector syntax (dependency references)
| Form | Meaning | Example |
|---|---|---|
| `art` | Whole artifact (coarse, fail-closed on any change). Prose elsewhere writes this as `selector="*"`. | `tpm_model` |
| `art#/json/pointer` | One leaf or subtree of a params file (RFC 6901 pointer) | `cooling#/flow_scale` |
| `art[col1,col2]` | Columns of a dataset (all row groups) | `measures[pm,coolant]` |

```python
# src/reval/domain/selectors.py
class Selector(Frozen):
    artifact_id: str
    pointer: str | None = None          # "/flow_scale"
    columns: tuple[str, ...] = ()       # sorted
    @classmethod
    def parse(cls, text: str) -> "Selector": ...   # raises ManifestError on bad syntax
    def render(self) -> str: ...                   # inverse of parse (canonical form; columns sorted)
    @property
    def is_whole(self) -> bool: ...                # no pointer and no columns
    def covers(self, other: "Selector") -> bool:
        """Overlap test (symmetric). True iff same artifact and one of:
        - either side is whole;
        - both are pointers and one is a segment-wise RFC 6901 prefix of the other
          ('/a' covers '/a/b'; '/coolant/flow' does NOT cover '/coolant/flow_lpm');
        - both list columns and the column sets intersect."""
```
Owner: task P2-02. `selector_hash` (which needs a `Snapshot`) is in `core/selectors.py`, owned by P2-03 (§4.0).

### 1.5 Graph node ids
`artifact:<id>`, `field:<selector>`, `assumption:<id>`, `requirement:<id>`, `subject:<id>`, `claim:<id>`, `evidence:<id>`, `producer:<id>`.

### 1.6 Determinism
No `datetime.now`, no `random` in core. Sort every output collection by id. CP-SAT uses `num_workers=1` and `random_seed=0`.

---

## 2. `reval.domain`

Enums `Verdict`, `Status`, `FreshnessClass`, `ReasonCode` already exist in `domain/status.py`. Import them from there; don't redefine them.

```python
# quantities.py
class Interval(Frozen):
    lo: float
    hi: float
    unit: str                                            # unit of lo/hi (the quantity's canonical unit)
    # validator: lo <= hi, both finite
    def widen(self, delta: float) -> "Interval": ...     # delta >= 0 (in the quantity's difference unit) else ValueError; [lo-δ, hi+δ]
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
    content_hash: str                       # "missing" if the file doesn't exist; folds upstream hashes when derived_from is set (§6)
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
    code_hash: str                        # §7 code_hash
    depends_on: tuple[str, ...]           # rendered selectors, sorted
    assumes: tuple[str, ...] = ()         # assumption ids, sorted
    predictors: tuple[str, ...] = ()      # ids of the model artifacts that produce the quantity (independence, docs/03 §3), sorted;
                                          # every entry must also appear (as artifact id) in depends_on

class Dependency(Frozen):
    selector: str                         # rendered Selector
    version_hash: str                     # selector_hash(snapshot, selector) at the snapshot the evidence was produced at (§4.0)

class Scope(Frozen):
    box: dict[str, tuple[float, float]] = {}
    assumption_ids: tuple[str, ...] = ()  # always ⊇ producer.assumes (set by run_producer, §7)

class Tolerance(Frozen):
    selector: str                         # must be a pointer selector, e.g. "cooling#/flow_scale"
    sensitivity: float                    # >= 0, RAW max |∂output/∂input| (no safety factor folded in)
    input_unit: str                       # unit of the field's values (YAML values are unitless; this declares them)
    output_unit: str                      # must equal difference_unit(quantity unit), else classify raises ValueError
    valid_range: tuple[float, float]      # both old AND new field values must lie inside
    safety_factor: float = 1.5            # κ >= 1; applied exactly once, at inflation time
    source: str                           # non-empty: how it was obtained
    assumption_id: str                    # required: the assumption backing the bound (docs/03 §4)

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
    claim_id: str                         # a waiver applies to exactly one claim
    requirement_hash: str                 # content_id(Requirement) at creation; a different hash → waiver INVALIDATED
    # The waiver Evidence's deps = union of the deps of all evidence for that claim at creation (so any upstream change stales it).

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
    derived_from_evidence: str | None = None   # set only on carried-forward evidence (materialized per assessment, never stored)
    waiver: Waiver | None = None               # required iff kind == WAIVER
    # No timestamps: id must be a pure function of content.

# policies.py
class EvidenceRequirement(Frozen):
    kind: ProducerKind
    min_fidelity: int = 0
    in_domain: bool = False
    independent_of: tuple[ProducerKind, ...] = ()

class Policy(Frozen):
    id: str
    alternatives: tuple[tuple[EvidenceRequirement, ...], ...]   # OR of ANDs; each clause 1..3 conjuncts

DEFAULT_POLICIES: dict[str, Policy]   # "low", "medium", "high" exactly as docs/03 §3 (including the analytic clauses)

# snapshot.py
class Snapshot(Frozen):
    id: str                               # == content_id(self, exclude={"id", "git_rev"}) — the ONLY definition (validator checks it)
    git_rev: str | None = None            # informational; never part of the id; null in reval.lock.json
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
    rows_bbox: dict[str, tuple[float, float]] | None = None
        # component-wise hull (min of lo, max of hi) over affected groups: ROWS_ADDED → new bboxes;
        # ROWS_REMOVED → old bboxes; ROWS_MODIFIED → hull of old AND new bboxes. Only variables present in all hulled bboxes.
    detail: str | None = None             # human-readable note (e.g. "claim added", "column set changed: +foo")

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
    evidence_id: str                      # for carried-forward items: the id of e′ (the derived item)
    verdict: Verdict
    freshness: FreshnessClass
    interval_used: Interval | None = None
    used_in_clause: bool = False
    derived_from_evidence: str | None = None   # original e.id for carried-forward items
    recorded_verdict: Verdict | None = None    # for INVALIDATED / CARRY_FORWARD items: verdict of the original recorded interval

class Assessment(Frozen):
    claim_id: str
    snapshot_id: str
    status: Status
    reasons: tuple[Reason, ...]           # sorted by (code, message)
    evidence: tuple[EvidenceUse, ...]     # sorted by evidence_id; includes INVALIDATED items (with recorded_verdict) for explanation
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
    id: str                               # f"{producer_id}@{subject_id}" for new runs; f"existing:{evidence_id}" for reuse
    producer_id: str
    subject_id: str
    cost: float                           # 0 for existing fresh PASS evidence
    satisfies: tuple[str, ...]            # obligation keys, sorted
    predictors: tuple[str, ...] = ()      # copied from the producer (for independence constraints)
    existing_evidence_id: str | None = None

class PlanningProblem(Frozen):
    snapshot_id: str
    claim_weights: dict[str, int]         # claims needing restoration -> integer weight (low 1, medium 3, high 10)
    clauses: dict[str, tuple[tuple[str, ...], ...]]   # claim_id -> per clause: ALL obligation keys of that clause
    obligations: dict[str, Obligation]
    candidates: tuple[CandidateRun, ...]  # sorted by id
    incompatible: tuple[tuple[str, str, str, str], ...] = ()
        # (candidate_j, obligation_o, candidate_j2, obligation_o2): x_{j,o} + x_{j2,o2} <= 1 (independence), sorted

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
    unrestorable: tuple[str, ...]         # no clause can be covered even with infinite budget
    deferred: tuple[str, ...] = ()        # restorable, but not covered within the budget (max_restored only)
    solver_status: str                    # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "GREEDY" | "ALL"
    reproducible: bool = True             # False when solver_status == "FEASIBLE" (time limit hit; result may vary)

# settings.py — engine knobs used by core, the SDK and the benchmark ablations (lives in domain so core may import it)
class ReValSettings(Frozen):
    field_level_selectors: bool = True    # A1: False → every dep is treated as whole-artifact
    tolerance_carry_forward: bool = True  # A2: False → field changes are never excused
    scope_freshness: bool = True          # A3: False → row changes are never excused
    ad_gate: Literal["strict", "relaxed", "off"] = "strict"   # A4 (relaxed = ≥ 99 % of timesteps inside)
    interval_method: Literal["conformal", "fixed_margin", "cqr"] = "conformal"   # A5 / A8
    planner: Literal["ilp", "greedy"] = "ilp"                 # A6
    kappa_override: float | None = None   # A7: replaces every Tolerance.safety_factor when set

DEFAULT_SETTINGS = ReValSettings()
```
`reval.domain.__init__` re-exports all public classes above. `reval.services` re-exports `ReValSettings`/`DEFAULT_SETTINGS`. Core functions that
honor settings take `settings: ReValSettings = DEFAULT_SETTINGS` as a keyword argument.

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
    # collects Producer metadata from the registry, merges policies, computes Snapshot.id (§2, D1).
```
`build_snapshot` has its own task (after P2-05 and P2-06), because it needs both the manifest loader and the producer registry.

---

## 4. `reval.core` (pure)

### 4.0 `selectors.py`
```python
def selector_hash(snapshot: Snapshot, selector: str) -> str: ...
    # whole → version.content_hash;
    # pointer → sha256 over sorted (k, h) of field_hashes with k == pointer or k.startswith(pointer + "/") (segment-wise);
    # columns → sha256 over sorted (k, h) of the "c=<col>" hashes for the listed columns;
    # artifact missing from snapshot, or content_hash == "missing" → "missing".
def derived_closure(snapshot: Snapshot, artifact_id: str) -> frozenset[str]: ...
    # transitive upstream artifact ids via Artifact.derived_from (excluding artifact_id itself)
```
Owner: task P2-03. `sdk/runner.py`, `core/freshness.py`, and services import it from here.

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
5. Manifest entities: any field difference → `REQUIREMENT_/ASSUMPTION_/POLICY_/SUBJECT_/CLAIM_CHANGED` (target = entity id). Add/remove uses the same kind
   with `detail="added"`/`"removed"` (there are no separate `*_ADDED` kinds for entities). For a requirement limit change, set old/new/delta.
6. Producer `code_hash` or `depends_on` differs → `PRODUCER_CODE_CHANGED` (target = producer id).
7. Anything not classifiable → `UNKNOWN`.

### 4.3 `freshness.py`
```python
@dataclass(frozen=True)
class FreshnessResult:
    evidence_id: str
    cls: FreshnessClass
    reasons: tuple[Reason, ...]
    inflation: float                    # 0.0 unless CARRY_FORWARD; in the quantity's difference unit (§1.3)
    relevant_changes: tuple[Change, ...]

def classify_evidence(e: Evidence, old: Snapshot, new: Snapshot, changes: ChangeSet) -> FreshnessResult: ...
def classify_all(evidence: Sequence[Evidence], snapshots: Mapping[str, Snapshot], new: Snapshot,
                 changesets: Mapping[str, ChangeSet]) -> dict[str, FreshnessResult]: ...
    # keyed by evidence id; snapshots/changesets keyed by evidence.provenance.snapshot_id.
    # If the old snapshot is missing → INVALIDATED with UNKNOWN_CHANGE (fail-closed).
def carry_forward(e: Evidence, fr: FreshnessResult, new: Snapshot) -> Evidence: ...
    # requires fr.cls == CARRY_FORWARD and e.result.interval; returns e′ with interval.widen(fr.inflation),
    # derived_from_evidence=e.id, provenance.snapshot_id=new.id, deps re-hashed against `new`, id recomputed.
    # e′ is passed to assess INSTEAD of e and is never stored (D5).
```
Notation: `deps*(e)` = the artifact ids of e's deps plus their `derived_closure` (§4.0).

**Algorithm for `classify_evidence` (in order):**
0. **Hard failures:** producer missing in `new` → INVALIDATED (`UNKNOWN_CHANGE`). For a waiver: `content_id(new.requirements[req of claim])` differs from
   `waiver.requirement_hash`, or the claim is gone → INVALIDATED (`REQUIREMENT_CHANGED`).
1. **Exact shortcut (`FRESH_EXACT`)** requires all of:
   - every `dep.version_hash == selector_hash(new, dep.selector)`;
   - `new.producers[e.producer_id].code_hash == e.provenance.producer_code_hash`;
   - no `ASSUMPTION_CHANGED` whose target ∈ `e.scope.assumption_ids ∪ {tol.assumption_id}`;
   - no `SUBJECT_CHANGED` whose target == `e.subject_id`;
   - no `UNKNOWN` change whose target artifact ∈ `deps*(e)` or whose target does not parse as a selector (D13).
2. **Relevance:** change *c* is relevant iff any of these hold:
   (a) `Selector.parse(c.target).covers(Selector.parse(dep.selector))` for some dep (for row changes with column lists on both sides, the columns must intersect);
   (b) `c.kind == ASSUMPTION_CHANGED` and `c.target ∈ scope.assumption_ids ∪ {tol.assumption_id}`;
   (c) `c.kind == PRODUCER_CODE_CHANGED` and `c.target == e.producer_id`;
   (d) `c.kind == UNKNOWN` and (its target artifact ∈ `deps*(e)` or its target is unparseable);
   (e) `c.kind == SUBJECT_CHANGED` and `c.target == e.subject_id` (D2);
   (f) `c` targets an artifact in `derived_closure` of some dep's artifact (D3: an upstream change of a derived artifact).
   REQUIREMENT/POLICY/CLAIM changes are **not** relevant to evidence freshness (status re-evaluation handles them; waivers are handled in step 0).
3. **Excuse each relevant change individually** (all must be excused, else INVALIDATED):
   - `ROWS_ADDED/MODIFIED/REMOVED` is excused iff it was matched via rule (a) by a dep that is a **column selector** on a dataset artifact (never a
     whole-artifact dep and never via rule (f)), `rows_bbox` is not None, and ≥ 1 variable *v* in both `rows_bbox` and `scope.box` has disjoint intervals (D12).
   - `FIELD_CHANGED` with numeric `old`, `new`, and `delta` is excused iff it was matched via rule (a) by a **pointer-selector** dep (never a whole-artifact dep, never via rule (f)),
     some tolerance has `tol.selector == c.target`, and both `old` and `new` are inside
     `tol.valid_range`. It contributes `tol.safety_factor * tol.sensitivity * abs(delta)` to inflation (κ applied once, D14).
     `tol.output_unit != difference_unit(e.result.unit)` → `ValueError`.
   - Every other relevant change (`UNKNOWN`, `ARTIFACT_*`, `FIELD_ADDED/REMOVED`, `ASSUMPTION_CHANGED`, `PRODUCER_CODE_CHANGED`, `SUBJECT_CHANGED`,
     rule-(f) matches, a field change with no tolerance) → not excused.
4. **Result:** any unexcused change → `INVALIDATED`, with one reason per unexcused change: `UNKNOWN_CHANGE` for UNKNOWN, `MISSING_TOLERANCE` for an untolerated
   field change, otherwise `EVIDENCE_INVALIDATED`. All excused and inflation > 0 → `CARRY_FORWARD`. All excused and inflation == 0 → `FRESH_OUT_OF_SCOPE`.
   `CARRY_FORWARD` with `e.result.interval is None` → `INVALIDATED` (`MISSING_TOLERANCE`).

### 4.4 `verdicts.py`
```python
def verdict(e: Evidence, req: Requirement) -> tuple[Verdict, tuple[Reason, ...]]: ...
```
- Units: `e.result.unit != req.unit` or `e.result.quantity != req.quantity` → `ValueError` (programming error).
- `WAIVER` → PASS.
- `ML_PREDICTION` with `in_domain is not True` → INCONCLUSIVE + `OUT_OF_DOMAIN` (detail = domain_report).
- Interval `[lo, hi]` = `result.interval`, or `[point, point]` when `uncertainty_kind == "exact"`.
  No interval and `point` is set (for example, an unbounded conformal quantile, see §5) → INCONCLUSIVE + `MARGIN_BELOW_UNCERTAINTY`.
  Neither interval nor point → INCONCLUSIVE + `NO_EVIDENCE`.
- `LE`: `hi <= L` → PASS. `lo > L` → FAIL. Else INCONCLUSIVE + `MARGIN_BELOW_UNCERTAINTY`.
- `GE`: `lo >= L` → PASS. `hi < L` → FAIL. Else INCONCLUSIVE + `MARGIN_BELOW_UNCERTAINTY`.

### 4.5 `status.py`
```python
@dataclass(frozen=True)
class AssessInput:
    evidence: Evidence                    # for CARRY_FORWARD: the derived e′ (never the original e)
    freshness: FreshnessClass
    original: Evidence | None = None      # for CARRY_FORWARD: the original e (to compute recorded_verdict); else None

def assess_claim(claim: Claim, snapshot: Snapshot, items: Sequence[AssessInput],
                 changes: ChangeSet | None = None) -> Assessment: ...
def assess_all(snapshot: Snapshot, items: Sequence[AssessInput],
               changes: ChangeSet | None = None) -> dict[str, Assessment]: ...
```
Status is **history-free** (D4). There is no `previous` parameter. Assessments from earlier snapshots are only used by services for display and diffs.

- **Inputs.** Only items whose `evidence.subject_id == claim.subject_id` and `result.quantity == requirement.quantity` are considered. Waivers count only if
  `waiver.claim_id == claim.id`. A `CARRY_FORWARD` item with `evidence.derived_from_evidence is None` or `original is None` → `ValueError`.
  INVALIDATED items are passed too. They never support anything, but they drive STALE.
- **Fresh** = freshness ∈ {FRESH_EXACT, FRESH_OUT_OF_SCOPE, CARRY_FORWARD}. **Eligible** = fresh and kind appears in some conjunct of the policy (matching waivers are always eligible).
- **Recorded verdict** of an INVALIDATED item = `verdict(e, requirement)` on its recorded result. For a CARRY_FORWARD item, it is `verdict(original, requirement)`.
- **Superseded:** an INVALIDATED item is superseded when a fresh item from the **same producer** for the same subject and quantity exists (the rerun replaced it).
  Superseded items are ignored by rules 3 and 5, so a rerun can clear a lost fail.
- **Rules, in order (first match wins):**
  1. **VIOLATED:** any eligible item has verdict FAIL. Reason codes: `CONFLICTING_EVIDENCE` if an eligible PASS also exists, plus the FAIL ids.
  2. **WAIVED:** an eligible matching waiver exists. Reason `WAIVER_APPLIED`. Its EvidenceUse has `used_in_clause=True`.
  3. **STALE (lost fail):** some non-superseded item with policy-eligible kind has `recorded_verdict == FAIL` and is now INVALIDATED, or is CARRY_FORWARD with a current verdict ≠ FAIL.
     Reason `EVIDENCE_INVALIDATED` with those ids, and `detail={"lost_fail": true}`.
  4. **SUPPORTED:** some clause is satisfied by fresh eligible PASS evidence (clause matching below). Reason `POLICY_SATISFIED`, with `satisfied_clause = k`.
  5. **STALE:** clause matching succeeds when every non-superseded INVALIDATED item, and every CARRY_FORWARD item, is evaluated at its **recorded** verdict
     (and the assignment uses ≥ 1 such item whose current verdict isn't PASS or which is INVALIDATED). Reason `EVIDENCE_INVALIDATED`, listing those ids.
     This covers support lost to invalidation and support lost to inflation (PASS → INCONCLUSIVE after carry-forward).
  6. **INCONCLUSIVE:** `NO_EVIDENCE` if there's no eligible item. Otherwise the union of the verdict reasons of the eligible items, plus `POLICY_UNMET` if some PASS exists but no clause is satisfied.
- **Clause matching:** for clause *k*, the candidates per conjunct are items with verdict PASS, matching kind, `fidelity >= min_fidelity`, and `result.in_domain is True` when
  `in_domain` is required. Try `itertools.product` over the candidate lists (each list sorted by evidence id). The assignment must use distinct evidence. For each conjunct
  with `independent_of`, its evidence must be **independent** of every assigned evidence whose kind is listed. Independent ⇔ different `producer_kind` **and** disjoint
  `snapshot.producers[pid].predictors` (D6). The first valid assignment (lowest clause index, then lexicographic ids) wins. Its uses get `used_in_clause=True`.
- If `changes` contains `REQUIREMENT_CHANGED` for the claim's requirement, add `REQUIREMENT_CHANGED` (informational) to the reasons.
- `input_hash = sha256_hex(canonical_json({"claim": claim, "requirement": req, "policy": policy, "items": [(evidence.id, freshness, interval, original id)] sorted}))`.
  It contains no history (I1, I2).

### 4.6 `planner.py`
```python
CRITICALITY_WEIGHT: dict[str, int] = {"low": 1, "medium": 3, "high": 10}

def build_problem(snapshot: Snapshot, assessments: Mapping[str, Assessment],
                  items: Sequence[AssessInput], *,
                  available: Callable[[str, str], bool],            # (producer_id, subject_id) -> runnable?
                  known_out_of_domain: frozenset[tuple[str, str]] = frozenset()) -> PlanningProblem: ...
def plan(problem: PlanningProblem, *, planner: Literal["ilp", "greedy", "all"] = "ilp",
         objective: Literal["min_cost", "max_restored"] = "min_cost", budget: float | None = None,
         max_time_s: float = 10.0) -> RevalidationPlan: ...
```
- **Claims to restore:** status ∈ {STALE, INCONCLUSIVE}. Every conjunct of every clause becomes an obligation (nothing is dropped, D7).
- **Lost-fail obligations (rule 3):** for each non-superseded lost-fail item of a claim (docs/03 §3 rule 3), add a **mandatory** obligation
  `rerun:<producer_id>@<subject_id>`. It can only be satisfied by the new-run candidate for that producer and subject, and every clause of the claim
  additionally requires it (`y_{c,k} ≤ x_{j_rerun}` for all k). If that candidate isn't available, the claim is `unrestorable`. Reuse at cost 0 never restores a lost-fail claim.
- **Reuse candidates:** each fresh eligible PASS item for the claim's subject becomes a candidate `existing:<evidence_id>` with cost 0, satisfying the obligations
  it matches (kind, fidelity, `in_domain`). Reuse is therefore decided inside the same matching as new runs.
- **New-run candidates:** `(producer P, subject S)` is generated iff `available(P.id, S.id)`, **no FRESH_EXACT evidence from P on S exists at this snapshot**
  (rerunning a deterministic producer would reproduce it; CARRY_FORWARD and FRESH_OUT_OF_SCOPE items stay rerunnable, because a rerun removes the
  inflation or refreshes the scope), and not (`P.kind == ML_PREDICTION` and `(P.id, S) in known_out_of_domain`) — regardless of the
  conjunct's `in_domain` flag. It satisfies obligation *o* iff `o`'s claim subject is S, the requirement quantity ∈ `P.quantities`, `P.kind == o.requirement.kind`,
  and `P.fidelity >= min_fidelity`.
- **Independence (`incompatible`):** for every clause and every conjunct pair (o, o′) where `o.requirement.independent_of` contains o′'s kind, and every candidate pair
  (j, j′) whose `predictors` intersect or whose producer kinds are equal → `x_{j,o} + x_{j′,o′} ≤ 1`.
- **ILP (CP-SAT):** integer costs `cost_int = round(cost * 100)`. Integer weights `w_c` from `CRITICALITY_WEIGHT`. Variables `z_j`, `x_{j,o}`, `y_{c,k}`, `u_c` (docs/04 A7):
  `x_{j,o} ≤ z_j`; `Σ_{o∈clause} x_{j,o} ≤ 1` (one run counts once per clause); `y_{c,k} ≤ Σ_j x_{j,o}` for each o in k; `Σ_k y_{c,k} + u_c ≥ 1`; the `incompatible` constraints.
  - `min_cost`: minimize `Σ cost_int z_j + M · Σ w_c u_c`, where `M = 1 + Σ_j cost_int`.
  - `max_restored`: subject to `Σ cost_int z_j ≤ round(budget * 100)`, minimize `(1 + Σ_j cost_int) · Σ w_c u_c + Σ cost_int z_j`. This is a single integer objective,
    lexicographic in effect.
  - Solver params: `num_workers=1`, `random_seed=0`, `max_time_in_seconds=max_time_s`. `solver_status` records CP-SAT's status. `FEASIBLE` (time limit hit) sets `reproducible=False`.
    Tests must assert `OPTIMAL`.
- **greedy:** repeat, picking the candidate with the max `(Σ weights of claims whose cheapest open clause loses an obligation) / max(cost, 0.01)` (ties → candidate id),
  respecting `incompatible`, until every claim has a fully covered clause or nothing improves. Then drop redundant runs in descending cost order.
- **all:** select every non-reuse candidate that satisfies ≥ 1 obligation, plus every reuse candidate.
- **`unrestorable`** = claims for which no clause can be covered by **all** candidates together (computed independently of the budget).
  **`deferred`** = claims that are restorable but left uncovered (`u_c = 1`) by the chosen plan. This is only non-empty for `max_restored` / greedy under a budget.
- `PlannedRun`s are produced only for new-run candidates. Reuse candidates appear in `chosen_clauses` bookkeeping via their obligations, not as runs.

---

## 5. `reval.uq` (numpy/scipy helpers for producers; pure)

Binding API (D20). Owners: P1-05 (`conformal.py`, `__init__.py`), P1-06 (`domain.py`). Phase-4 tasks only **extend** this module (for example `GroupedSplitConformal`).
Tests: `tests/unit/uq/test_conformal.py`, `tests/unit/uq/test_domain.py`.

```python
# conformal.py
def conformal_quantile(scores: np.ndarray, alpha: float) -> float: ...
    # n = len(scores); k = ceil((n + 1) * (1 - alpha)); return inf if k > n else sorted(scores)[k - 1]
    # (so n < ceil(1/alpha) - 1 gives inf: unbounded interval)
class SplitConformal:
    def __init__(self, alpha: float) -> None: ...
    def fit(self, y_true: np.ndarray, y_pred: np.ndarray) -> "SplitConformal": ...   # scores = |y_true - y_pred|
    def fit_scores(self, scores: np.ndarray) -> "SplitConformal": ...                 # precomputed nonnegative scores
    def interval(self, y_pred: float) -> tuple[float, float] | None: ...             # None when q is inf
    @property
    def q(self) -> float: ...
    @property
    def n(self) -> int: ...
def empirical_coverage(y_true: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float: ...
```
**Producer rule:** when `interval(...)` is `None` (q̂ = inf), the ML producer emits `interval=None`, `point=<prediction>`, and `uncertainty_kind="none"`.
The verdict is then INCONCLUSIVE with `MARGIN_BELOW_UNCERTAINTY` (§4.4).

```python
# domain.py
class DomainReport(Frozen):
    inside: bool
    first_violation: int | None           # row index of the first violating timestep
    violating_features: tuple[str, ...]   # box violations at first_violation, sorted
    frac_outside: float
    max_knn_distance: float
    threshold: float                      # τ
    box: dict[str, tuple[float, float]]
    def to_dict(self) -> dict[str, Any]: ...   # == model_dump(mode="json"); goes into EvidenceResult.domain_report
class ApplicabilityDomain:
    def __init__(self, feature_names: Sequence[str], k: int = 10,
                 box_quantiles: tuple[float, float] = (0.005, 0.995), dist_quantile: float = 0.99,
                 max_train_rows: int = 200_000) -> None: ...
    def fit(self, X_train: np.ndarray, X_calib: np.ndarray) -> "ApplicabilityDomain": ...
        # standardize on train; deterministic subsample (default_rng(0)) to max_train_rows; cKDTree; box from train quantiles; τ from calib mean kNN distance
    def check(self, X: np.ndarray, *, min_inside_frac: float = 1.0) -> DomainReport: ...
        # strict (default, 1.0): inside iff every row passes; relaxed: inside iff (1 - frac_outside) >= min_inside_frac
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
- **Upstream folding (all hashers, D3):** let `own` be the hasher's own content hash as described below. If `artifact.derived_from` is non-empty, then
  `content_hash = sha256(own + "|" + "|".join(upstream[a].content_hash for a in sorted(derived_from)))`, otherwise `content_hash = own`.
  `field_hashes` always stay own-only. So a derived params file (for example, `lptn.yaml` identified from `measures`) changes its content hash whenever its source changes,
  even if it wasn't regenerated (constructive trace, fail-closed).
- **file:** own = sha256 of the bytes. No fields.
- **yaml-fields:** `yaml.safe_load`. Flatten to RFC 6901 pointers (lists use indices). `field_hashes[ptr] = sha256(canonical_json(leaf))`. Scalar leaves go into `field_values`.
  own = `sha256(canonical_json(doc))`.
- **dataframe:** lazy-import pandas (raise `MissingExtraError("motor")` if absent). Reads `.parquet` or `.csv`. Group column = `artifact.key[0]` (required).
  For each group *g* (stringified) and column *c*: `sha256(pd.util.hash_pandas_object(col_values, index=False).values.tobytes())` → `g=<g>/c=<c>`.
  `c=<c>` = sha256 over the concatenated group hashes in sorted group order. `row_groups[g]` has `n_rows` and a bbox over numeric columns.
  own = sha256 over the sorted `field_hashes` items.
- **model:** own = sha256 of the file bytes. No fields. (With upstream folding, an upstream change changes the model's hash even if it wasn't retrained.)
- Missing file → `ArtifactVersion(content_hash="missing")`.
- Optional cache `.reval/hash-cache.json` keyed by `(path, size, mtime_ns, hasher)` → cached `ArtifactVersion` (task P2-04 may defer it).

---

## 7. `reval.sdk`

```python
def producer(*, kind: ProducerKind | str, quantity: str | Sequence[str], cost: float, fidelity: int | None = None,
             depends_on: Sequence[str] = (), assumes: Sequence[str] = (), predictors: Sequence[str] = (),
             available_for: Callable[[Subject], bool] | None = None, id: str | None = None,
             registry: "ProducerRegistry | None" = None) -> Callable[[ProducerFn], ProducerFn]: ...
    # predictors: model artifact ids whose output IS the quantity (e.g. ["tpm_model"] for ML; ["lptn"] for physics);
    # each must be the artifact of some depends_on selector, else ValueError.
ProducerFn = Callable[[Subject, "Context"], "ProducerOutput"]

class RegisteredProducer(NamedTuple):
    meta: Producer
    fn: ProducerFn
    available_for: Callable[[Subject], bool] | None

class ProducerRegistry:
    def register(self, rp: RegisteredProducer) -> None: ...   # duplicate id → ValueError
    def get(self, producer_id: str) -> RegisteredProducer: ...
    def all(self) -> tuple[RegisteredProducer, ...]: ...      # sorted by id
    def load_modules(self, modules: Sequence[str], project_root: Path) -> None: ...
        # sys.path insert + importlib; then (re)computes every registered Producer.code_hash with code_hash(fn, project_root).
        # The decorator registers with a placeholder code_hash; nothing may read it before load_modules.
DEFAULT_REGISTRY: ProducerRegistry

def code_hash(fn: Callable[..., Any], project_root: Path) -> str: ...
    # D16: pkg = top-level package of fn.__module__; files = sorted .py files under <dir of pkg> (relative POSIX paths);
    # sha256 over b"".join(relpath.encode() + b"\0" + bytes + b"\0" for each) + qualname.encode().
    # A module outside project_root (or a single-file module) hashes just that file. So editing a helper module (motor/lptn.py) changes the hash.

class Context:
    def __init__(self, project_root: Path, snapshot: Snapshot, producer: Producer,
                 settings: ReValSettings = DEFAULT_SETTINGS) -> None: ...
    def load(self, artifact_id: str) -> Any: ...
        # D11: allowed iff depends_on contains the WHOLE artifact selector (bare `artifact_id`) → full object, or
        #      column selectors on it → for dataframes, only the declared columns + artifact.key columns are returned.
        # Only pointer deps on it → UndeclaredDependencyError (use ctx.param). No dep at all → UndeclaredDependencyError.
        # .joblib/.pkl → joblib.load; .yaml/.yml → yaml.safe_load; .parquet → pandas.read_parquet; .csv → pandas.read_csv; else bytes.
    def param(self, selector: str) -> Any: ...     # pointer value from a params artifact; selector must be covered by a declared dep
    def assumption(self, assumption_id: str) -> Assumption: ...   # must be in `assumes`
    @property
    def seed(self) -> int: ...                     # deterministic: int(sha256(producer.id + snapshot.id)[:8], 16)
    @property
    def settings(self) -> ReValSettings: ...       # passed in by the runner (default DEFAULT_SETTINGS); producers read ad_gate / interval_method here

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
    # calls fn; one Evidence per result. deps = [Dependency(sel, selector_hash(snapshot, sel)) for sel in depends_on] (core/selectors.py);
    # scope = output.scope with assumption_ids = sorted(set(output.scope.assumption_ids) | set(producer.assumes)) (D9);
    # provenance(producer_code_hash, snapshot.id, env=installed versions of reval/numpy/scipy/sklearn/pandas if present, seed=ctx.seed);
    # cost = producer cost; id = content_id. Rejects results whose quantity isn't in producer.quantities (ProducerError).
    # Waiver producers: requires output.waiver with claim_id/requirement_hash; deps = union of deps of the claim's current evidence (D10).
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
    def put_assessments(self, snapshot_id: str, items: Sequence[Assessment]) -> int: ...
        # append-only (D18): writes a new batch with seq = max(seq for snapshot_id) + 1; returns seq. Never updates old rows.
    def get_assessments(self, snapshot_id: str, *, seq: int | None = None) -> dict[str, Assessment]: ...   # default: highest seq
    def latest_assessed_snapshot(self, *, before: str | None = None) -> str | None: ...
        # by the created_seq of the most recent assessment batch (not of the snapshot row), so revisiting an old snapshot works
    def put_plan(self, p: RevalidationPlan) -> None: ...
    def get_plan(self, plan_id: str) -> RevalidationPlan | None: ...
    def latest_plan(self, snapshot_id: str) -> RevalidationPlan | None: ...
    def put_job(self, job: Job) -> None: ...                    # insert only
    def update_job_state(self, job_id: str, state: JobState, *, result: dict[str, Any] | None = None) -> None: ...
        # the ONLY in-place update in the store (AGENTS rule 5 exception)
    def get_job(self, job_id: str) -> Job | None: ...
    def put_report(self, report_id: str, snapshot_id: str, body: dict[str, Any]) -> None: ...   # idempotent on id
    def get_report(self, report_id: str) -> dict[str, Any] | None: ...

class JobState(StrEnum): QUEUED="queued"; RUNNING="running"; SUCCEEDED="succeeded"; FAILED="failed"
class Job(Frozen):            # store/jobs.py
    id: str
    kind: Literal["run_plan", "run"]
    state: JobState
    payload: dict[str, Any]
    result: dict[str, Any] | None = None

class SqlStore(Store):
    def __init__(self, url: str) -> None: ...                  # metadata.create_all(engine) for now; Alembic added in P6
def open_store(project_root: Path) -> SqlStore: ...
    # url = env REVAL_DATABASE_URL or f"sqlite:///{project_root/'.reval'/'reval.db'}" (mkdir .reval)
```
Tables (SQLAlchemy Core or ORM, module `store/tables.py`):
`snapshots(id PK, git_rev, created_seq INT autoinc unique, body TEXT)`, `evidence(id PK, subject_id IDX, producer_id IDX, snapshot_id IDX, created_seq, body)`,
`assessments(snapshot_id, claim_id, seq, created_seq, status, input_hash, body, PK(snapshot_id, claim_id, seq))`, `plans(id PK, snapshot_id IDX, created_seq, body)`,
`jobs(id PK, kind, state, payload, result, created_seq)`, `reports(id PK, snapshot_id IDX, body)`. `body` = `canonical_json(obj).decode()`. Read back with `Model.model_validate_json`.
`created_seq` is a store-assigned monotone integer (never a wall clock).

---

## 9. `reval.gitio`

```python
LOCK_FILE = "reval.lock.json"
def write_lock(project_root: Path, snapshot: Snapshot) -> Path: ...
    # json.dumps(snapshot.model_copy(update={"git_rev": None}).model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=False) + "\n"; LF newlines
def read_lock(path: Path) -> Snapshot: ...
    # missing → LockNotFoundError; recomputes content_id(exclude={"id","git_rev"}) and raises StoreError if != stored id (D1)
def parse_lock(data: bytes, source: str) -> Snapshot: ...   # same checks, for bytes from `git show`
def read_file_at_rev(repo_root: Path, rev: str, rel_path: str) -> bytes: ...
    # subprocess ["git", "-C", repo_root, "show", f"{rev}:{rel_path}"]; nonzero → GitError (message includes stderr)
def snapshot_at_rev(repo_root: Path, rev: str, project_subdir: str = ".") -> Snapshot: ...
    # parses the lock at rev (no lock at that rev → LockNotFoundError); returns it with git_rev = resolved sha (the id is unchanged)
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
    affected_claims: tuple[str, ...]     # status changed, or any evidence for the claim not FRESH_EXACT

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
`assess` steps: (1) Store the snapshot. (2) Load all evidence. (3) Group it by `provenance.snapshot_id`. Get each old snapshot from the store. A missing old snapshot → INVALIDATED (`UNKNOWN_CHANGE`).
(4) Compute `diff_snapshots(old, current)` once per group. (5) `classify_all`. (6) Build `AssessInput`s: CARRY_FORWARD items become `AssessInput(carry_forward(e, fr, current), CARRY_FORWARD, original=e)`.
Everything else is `AssessInput(e, cls)`. Carried items are **not** stored (D5). (7) `assess_all(current, items, changes)`, where `changes` = the diff from the previous assessed snapshot,
for the `REQUIREMENT_CHANGED` note only. (8) Store the assessments as a new batch (D18).
`clock: Callable[[], datetime]` is injected into `Project.open(root, *, clock=...)` and used only for report timestamps (D19). Core never sees it.
`available(P, S)` = `registry.get(P).available_for(subject)` if set, else True. `known_out_of_domain` = (producer, subject) pairs whose latest fresh ML evidence has `in_domain is False`.

**Report hashing (D19):** `report_hash = content_id(report, exclude={"report_hash", "report_id", "created_at"})`, and `report_id = report_hash[:16]`. Two reports of the same state
therefore have the same hash, even when `created_at` differs.

---

## 11. CLI

Commands, options, and exit codes are exactly as in `docs/09-api-and-ui.md` (`init, snapshot [--write|--check], status, diff, plan, run, explain, report, graph, serve, version`).
`--project PATH` (default: cwd) on every command. Output: Rich tables for humans, `--format json` emits `canonical_json` of the result.

**API (D27):** single project. Routes keep the `/projects/{p}` prefix for forward compatibility, but only `p = "default"` exists. Its root comes from `REVAL_PROJECT_ROOT`
(default: cwd). Any other `p` → 404.

---

## 12. Motor example (`examples/motor_thermal/motor/`)

This section matches `docs/tasks/phase-1-motor.md` (D21). Where they differ, this section wins. `pytest` config adds `pythonpath = ["src", ".", "examples/motor_thermal"]`
with `--import-mode=importlib`. Tests that need the real dataset are marked `@pytest.mark.data` and skip if `data/processed/measures.parquet` is absent.
Motor tests live in `tests/unit/motor/` (that directory has **no** `__init__.py`, so it can't shadow the `motor` package).

```python
# data.py
EXPECTED_COLUMNS: tuple[str, ...] = ("u_q", "coolant", "stator_winding", "u_d", "stator_tooth", "motor_speed", "i_d", "i_q",
                                     "pm", "stator_yoke", "ambient", "torque", "profile_id")
def load_raw(path: Path) -> pd.DataFrame: ...                   # order-insensitive schema check → SchemaError (lists missing/extra)
def validate(df: pd.DataFrame) -> None: ...                     # no NaNs; integer profile_id; ≥ 1 row per profile → SchemaError
def prepare(raw_csv: Path, out_parquet: Path) -> Path: ...      # load → validate → add t (s, 0.5 s steps, restarts per profile) → sort (profile_id, t) → parquet

# splits.py
@dataclass(frozen=True)
class Splits:
    train: tuple[int, ...]; calib: tuple[int, ...]; test: tuple[int, ...]; reserve: tuple[int, ...]
    def of(self, profile_id: int) -> str: ...
def make_splits(summary: pd.DataFrame, seed: int, test_ids: Sequence[int] | None,
                fractions: tuple[float, float, float] = (0.65, 0.15, 0.20), n_reserve: int = 3) -> Splits: ...
def save_splits(splits: Splits, path: Path, *, seed: int, source_note: str) -> None: ...
def load_splits(path: Path) -> Splits: ...                      # asserts pairwise disjointness
def split_frame(df: pd.DataFrame, splits: Splits, name: Literal["train", "calib", "test", "reserve"]) -> pd.DataFrame: ...

# features.py
INPUT_COLUMNS = ("u_q", "u_d", "i_q", "i_d", "motor_speed", "coolant", "ambient")   # torque is NOT an input (it is itself an estimate)
DERIVED = ("i_s", "u_s", "p_el", "i_s_x_w")
EWMA_SPANS: tuple[int, ...] = (1320, 3360, 6360, 9480)          # samples at 2 Hz; a parameter
def add_derived(df: pd.DataFrame) -> pd.DataFrame: ...
def add_ewma(df: pd.DataFrame, cols: Sequence[str], spans: Sequence[int]) -> pd.DataFrame: ...
    # per profile (groupby("profile_id")), ewm(span=s, adjust=False): causal and recursive, matches real-time estimation; names "{col}_ewm{span}"
def make_features(df: pd.DataFrame, spans: Sequence[int] = EWMA_SPANS) -> tuple[pd.DataFrame, list[str]]: ...

# models.py
TARGETS = ("pm", "stator_winding")
class TrajectoryModel:
    kind: Literal["ridge", "hgb", "mlp"]
    feature_names: list[str]
    def fit(self, df_train: pd.DataFrame) -> "TrajectoryModel": ...
    def predict(self, df: pd.DataFrame) -> pd.DataFrame: ...     # one column per target
def peaks(y: pd.Series, profile_ids: pd.Series, window_rows: int) -> np.ndarray: ...   # non-overlapping per-profile windows; trailing partial dropped
def evaluate(model: TrajectoryModel, df_test: pd.DataFrame, window_rows: int) -> dict[str, Any]: ...
def save(model: TrajectoryModel, path: Path, *, meta: Mapping[str, Any]) -> None: ...   # joblib + sidecar .json
def load(path: Path) -> TrajectoryModel: ...

# conformal.py (motor-specific wrapper around reval.uq.SplitConformal)
LENGTH_CLASSES = {"short": 1200, "medium": 3600, "long": 7200}  # window rows (10 / 30 / 60 min at 2 Hz)
class PeakConformal:
    def fit(self, model: TrajectoryModel, df_calib: pd.DataFrame, alpha: float) -> "PeakConformal": ...   # one SplitConformal per (target, length class)
    def interval(self, target: str, pred_peak: float, length_class: str) -> tuple[float, float] | None: ...  # None if q̂ = inf
    def coverage(self, model: TrajectoryModel, df_test: pd.DataFrame) -> dict[str, dict[str, float]]: ...

# lptn.py
NODES = ("pm", "stator_yoke", "stator_tooth", "stator_winding")
@dataclass(frozen=True)
class LPTNParams:
    C: dict[str, float]; R: dict[tuple[str, str], float]
    k_cu: float; alpha_cu: float; k_fe1: float; k_fe2: float; k_pm: float
def r_coolant(r_ic_nominal: float, flow_scale: float) -> float: ...   # R_ic ∝ flow_scale ** -0.8 (forced convection; source cited in docstring)
def losses(i_s, u_s, w, theta_sw, p: LPTNParams) -> dict[str, np.ndarray]: ...
def simulate(inputs: pd.DataFrame, p: LPTNParams, theta0: Mapping[str, float] | None = None, dt: float = 0.5,
             *, flow_scale: float = 1.0) -> pd.DataFrame: ...   # one profile; explicit Euler; columns = NODES
def identify(df_train: pd.DataFrame, p0: LPTNParams, bounds: Mapping[str, tuple[float, float]],
             max_profiles: int | None = None, seed: int = 0) -> tuple[LPTNParams, dict[str, Any]]: ...
def model_form_band(p: LPTNParams, df_test: pd.DataFrame, window_rows: int) -> dict[str, float]: ...   # per node, K
def load_params(path: Path) -> LPTNParams: ...
def dump_params(p: LPTNParams, path: Path) -> None: ...          # flat pointer-friendly keys (/R/sw_st, /C/pm, /loss/k_cu)

# drive_map.py
class DriveMap:
    def fit(self, df_train: pd.DataFrame) -> "DriveMap": ...
    def to_inputs(self, torque: np.ndarray, speed: np.ndarray, coolant: float | np.ndarray,
                  ambient: float | np.ndarray) -> pd.DataFrame: ...                 # INPUT_COLUMNS at 2 Hz
    def domain_report(self, torque: np.ndarray, speed: np.ndarray) -> DomainReport: ...

# cycles.py
def blocks(params: Mapping[str, Any]) -> pd.DataFrame: ...       # {"blocks": [[torque_Nm, speed_rpm, duration_s], ...], "coolant", "ambient"} → torque, motor_speed, coolant, ambient, t
def recorded(profile_id: int, start_s: float, duration_s: float, df: pd.DataFrame) -> pd.DataFrame: ...   # real segment; test profiles only (R5)
def length_class(duration_s: float) -> Literal["short", "medium", "long"]: ...
def make_library(seed: int, splits: Splits) -> list[dict[str, Any]]: ...  # 40 parametric + 40 recorded (from `test` only; never `reserve`)

# optimizer.py
@dataclass(frozen=True)
class OptResult:
    theta: np.ndarray; subject_params: dict[str, Any]; pred_peak: float; upper: float | None; ad_report: DomainReport
def optimize(variant: Literal["O1", "O2", "O3"], model: TrajectoryModel, conformal: PeakConformal, ad: ApplicabilityDomain,
             drive_map: DriveMap, limits: Mapping[str, float], bounds: Sequence[tuple[float, float]], seed: int = 0) -> OptResult: ...

# producers.py — registered with @reval.producer. Names are binding:
#   predict_pm_peak_<model>, predict_sw_peak_<model>   (ML_PREDICTION, <model> in ridge|hgb|mlp; predictors=["tpm_<model>"] / ["tsw_<model>"])
#   lptn_sim            (PHYSICS_SIM, predictors=["lptn"]; depends_on = pointer deps "lptn#/R", "lptn#/C", "lptn#/loss" (never the whole
#                        "lptn", so tolerances on its leaves can apply), "drive_map", "cooling#/flow_scale")
#   bench_measure       (MEASUREMENT, predictors=[]; available_for = recorded test cycles in Tier A)
#   shaft_check         (ANALYTIC, fidelity 3), current_limit_check (ANALYTIC, fidelity 3, through the drive map)
# Coolant flow enters only via params/cooling.yaml#/flow_scale (dimensionless, nominal 1.0). ML producers declare it as a pointer
# dependency without a tolerance (fail-closed). lptn_sim declares it with a tolerance from sensitivities.py.

# sensitivities.py
def estimate_tolerances(params: LPTNParams, field: str, grid: Sequence[float], cycles: Sequence[Mapping[str, Any]],
                        *, assumption_id: str, kappa: float = 1.5) -> list[Tolerance]: ...
    # sensitivity = RAW max |Δpeak/Δfield| by central differences over grid × cycles; safety_factor = kappa (applied later, once: D14)
```

---

## 13. Errors (`reval/errors.py`, owner: task P2-01)

```python
class RevalError(Exception): ...
class ManifestError(RevalError): ...            # path, message, location
class UndeclaredDependencyError(RevalError): ...
class ProducerError(RevalError): ...
class MissingExtraError(RevalError): ...        # message: pip install "reval[<extra>]"
class GitError(RevalError): ...
class LockNotFoundError(GitError): ...          # no reval.lock.json at a revision / path
class StoreError(RevalError): ...
class SchemaError(RevalError): ...              # motor data schema mismatch
```
CLI maps `RevalError` → exit code 3 with a one-line message. Anything else is a bug (traceback).
