# Phase 2 — Core engine (roadmap weeks 7–10)

**Binding spec:** `docs/10-interfaces.md` (module paths, class fields, signatures). `docs/03-domain-model.md` is the semantic contract.
If the two disagree, stop and log it in `docs/log/questions.md`. Conventions: see the header of `phase-0-foundations.md`.
All `src/reval/domain` and `src/reval/core` code passes `mypy --strict`. The enums `Verdict`, `Status`, `FreshnessClass`, and `ReasonCode` **already exist**
in `src/reval/domain/status.py`. Import them; never redefine them.

**The test fixture project** (used from here to Phase 6; there is no other fixture project) is `tests/fixtures/mini_project/`. P2-05 creates it without
producers, and P2-06 adds its producers module. Its contents (D24):
- `reval.yaml` with `quantities: {temp_peak: degC, shaft_d: mm}` and `producers: [mini.producers]`.
- Artifacts: `params` (params, `params/params.yaml` with leaves `/load/scale: 1.0`, `/shaft/d_mm: 30.00`, `/sim/gain: 2.0`);
  `data` (dataset, `data/data.csv`, key `[group]`, columns `group, x, temp`, 3 groups × 20 rows); `surrogate` (model, `models/surrogate.json`,
  `derived_from: [data]`, a tiny JSON with a slope and an intercept).
- Assumptions: `A-ambient` (variable `ambient`, degC, bounds [10, 40]) and `A-sim-sens` (backs the tolerance on `/load/scale`).
- Requirements: `R-TEMP` (temp_peak ≤ 80 degC, **medium**), `R-TEMP-HI` (temp_peak ≤ 80 degC, **high**), `R-SHAFT` (shaft_d ≤ 30.05 mm, **low**).
- Subjects: `S1`, `S2` (duty_cycle, params `{"load": [..]}`), and `D1` (design, for the shaft).
- Claims: `C-S1-TEMP` (R-TEMP, S1), `C-S2-TEMP` (R-TEMP, S2), `C-S1-HI` (R-TEMP-HI, S1), `C-SHAFT` (R-SHAFT, D1).
- Producers (P2-06): `predict_temp` (ML, predictors `[surrogate]`, depends on `surrogate`, `params#/load/scale`, `data[temp,x]`, conformal-style interval, `in_domain` True for S1
  and False for S2); `sim_temp` (PHYSICS, predictors `[params]`, depends on `params#/load/scale` and `params#/sim/gain`, with a tolerance on `params#/load/scale`,
  `assumption_id="A-sim-sens"`); `measure_temp` (MEASUREMENT, `available_for` = S1 only, depends on `data[temp]`); `shaft_check` (ANALYTIC, depends on `params#/shaft/d_mm`).
  Every producer is a deterministic arithmetic function of the params and subject, so expected statuses can be written down by hand. Put the hand-computed
  expected statuses in `tests/fixtures/mini_project/EXPECTED.md`.

---

## P2-01 — Domain base, intervals, canonical JSON, errors
- **Owner:** sonnet · **Depends on:** P0-01 · **Read first:** `docs/10` §1, §2 (`quantities.py`), §13, ADR 0001
- **Files:** `src/reval/domain/base.py`, `src/reval/domain/quantities.py`, `src/reval/core/canonical.py`, `src/reval/errors.py`, `tests/unit/core/test_canonical.py`, `tests/unit/domain/test_quantities.py`
- **Spec:** `class Frozen(BaseModel)` with `ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=False)`. `Interval(lo, hi, unit)` with a validator
  (`lo <= hi`, both finite), `widen(delta)` (`delta >= 0`, else `ValueError`), and `width`. `canonical_json`, `sha256_hex`, `content_id(obj, *, exclude=frozenset({"id"}))`,
  and `difference_unit(unit)` (`degC` → `K`, otherwise unchanged), exactly as `docs/10` §1.2–1.3. `reval/errors.py` defines all nine classes in `docs/10` §13,
  including `LockNotFoundError(GitError)` and `SchemaError`. `MissingExtraError(extra)` formats its message as `pip install "reval[<extra>]"`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_canonical.py tests/unit/domain/test_quantities.py`: key order doesn't matter; two constructions give identical bytes;
  `Interval(lo=2, hi=1, unit="K")` raises; `widen(-1)` raises; NaN and inf are rejected; `difference_unit("degC") == "K"` and `difference_unit("mm") == "mm"`;
  `issubclass(LockNotFoundError, GitError)`. `tests/unit/test_architecture.py` still passes.

## P2-02 — Selectors, artifacts, engineering entities
- **Owner:** sonnet · **Depends on:** P2-01 · **Read first:** `docs/03` §1, `docs/10` §1.4, §2 (`artifacts.py`, `engineering.py`)
- **Files:** `src/reval/domain/selectors.py`, `src/reval/domain/artifacts.py`, `src/reval/domain/engineering.py`, `tests/unit/domain/test_selectors.py`, `tests/unit/domain/test_engineering.py`
- **Spec:** `Selector` exactly as `docs/10` §1.4: `parse` (raises `ManifestError` on bad syntax), `render` (the canonical inverse, with columns sorted), `is_whole`, and `covers`
  (symmetric overlap, **segment-wise** RFC 6901 prefix). `ArtifactKind`, `Artifact`, `RowGroupInfo`, `ArtifactVersion`, `Assumption` (validator: exactly one of `bounds` or `value[, tol]`),
  `Criticality`, `Comparator`, `Requirement`, `SubjectKind`, `Subject`, and `Claim`, exactly as `docs/10` §2.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/domain/test_selectors.py tests/unit/domain/test_engineering.py`: a selector parse table with ≥ 10 cases, including
  errors and `'/coolant/flow'` not covering `'/coolant/flow_lpm'`; `covers` is symmetric (a Hypothesis test); `parse(render(s)) == s`; the Assumption validator rejects both or neither;
  every entity round-trips through `model_validate(model_dump())`.

## P2-14 — Evidence, producers, policies
- **Owner:** sonnet · **Depends on:** P2-02 · **Read first:** `docs/03` §2–3, `docs/10` §2 (`evidence.py`, `policies.py`)
- **Files:** `src/reval/domain/evidence.py`, `src/reval/domain/policies.py`, `tests/unit/domain/test_evidence.py`, `tests/unit/domain/test_policies.py`
- **Spec:** `ProducerKind`, `DEFAULT_FIDELITY`, `Producer` (validator: every `predictors` entry appears as the artifact of some `depends_on` selector), `Dependency`, `Scope`,
  `Tolerance` (`sensitivity >= 0`, `safety_factor >= 1`, non-empty `source`, required `assumption_id`, the selector must be a pointer selector), `Provenance`, `EvidenceResult`,
  `Waiver` (non-empty `justification`, `claim_id`, `requirement_hash`), and `Evidence` (`waiver` required iff kind is WAIVER; `id == content_id(self)`, enforced by a validator
  or factory, your choice; tests assert the equality). `EvidenceRequirement`, `Policy`, and `DEFAULT_POLICIES` (low/medium/high **including the analytic clauses**, docs/03 §3).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/domain/test_evidence.py tests/unit/domain/test_policies.py`: round trips; `e.id == content_id(e)`; changing any field changes the id;
  a `Producer` whose predictor isn't a dependency raises; `DEFAULT_POLICIES["low"]` contains an `[analytic]` clause; `DEFAULT_POLICIES["high"]` has 3 clauses.

## P2-03 — Snapshot, changes, assessment, plan models + `core/selectors.py`
- **Owner:** sonnet · **Depends on:** P2-14 · **Read first:** `docs/10` §2 (`snapshot.py` … `plan.py`), §4.0, ADR 0005
- **Files:** `src/reval/domain/{snapshot,changes,assessment,plan}.py`, `src/reval/domain/__init__.py` (re-export everything in §2), `src/reval/core/selectors.py`,
  `tests/unit/domain/test_snapshot.py`, `tests/unit/core/test_selectors_hash.py`
- **Spec:** every model in `docs/10` §2 from `Snapshot` to `RevalidationPlan`, including `Change.detail`, `EvidenceUse.derived_from_evidence` and `recorded_verdict`, `RevalidationPlan.deferred` and `reproducible`.
  The `Snapshot` validator checks `id == content_id(self, exclude={"id", "git_rev"})`. `Snapshot.policy_for(claim_id)` falls back to `requirement.criticality.value`.
  `core/selectors.py`: `selector_hash(snapshot, selector)` and `derived_closure(snapshot, artifact_id)` exactly as `docs/10` §4.0.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/domain/test_snapshot.py tests/unit/core/test_selectors_hash.py`: the snapshot id is stable under dict insertion order and **ignores `git_rev`**;
  a wrong id raises; `selector_hash` cases for a params pointer (segment-wise subtree), dataset columns, the whole artifact, and a missing artifact (`"missing"`); `derived_closure` is transitive;
  every model round-trips through JSON.

## P2-04 — Hashers (`reval.hashing`)
- **Owner:** sonnet · **Depends on:** P2-03 · **Read first:** `docs/04` A1, `docs/10` §6
- **Files:** `src/reval/hashing/{__init__,base,file,yaml_fields,dataframe,model}.py`, `tests/unit/hashing/test_hashers.py`
- **Spec:** `Hasher` protocol, `HASHERS`, and `hash_artifact(artifact, root, upstream)` exactly as `docs/10` §6, including **upstream folding for every hasher** when
  `derived_from` is non-empty (D3). The dataframe hasher lazy-imports pandas and raises `MissingExtraError("motor")` when it's missing. A missing file gives
  `content_hash="missing"`. The optional cache may be deferred (note it in the commit body if so).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/hashing`: editing one YAML leaf changes exactly one field hash; modifying one group's `temp` changes only `g=<g>/c=temp` and `c=temp`;
  row order within a group **does** change the hash (time series; document why); an upstream change alters a derived artifact's `content_hash` for **both** a model and a params
  artifact, with the file unchanged, while its `field_hashes` don't change.

## P2-05 — Manifest schema + loader with units + fixture project
- **Owner:** sonnet · **Depends on:** P2-03 · **Read first:** `docs/03` §8, `docs/10` §3
- **Files:** `src/reval/manifest/{__init__,schema,loader,units}.py`, `tests/unit/manifest/test_loader.py`, `tests/fixtures/mini_project/` (everything in the phase header **except** `mini/producers.py`)
- **Spec:** `ManifestModel` (pydantic, `extra="forbid"`), `load_manifest(path) -> ManifestModel`, and `manifest_hash(path) -> str`, exactly as `docs/10` §3. Unit conversion with
  `pint` in `units.py`: limits are absolute and use `Quantity(v, unit).to(canonical)`. Errors are `ManifestError(path, message, location)`. `subjects:` may also be given as
  `subjects_file: subjects.yaml` (relative to the manifest). The loader does **not** import producer modules.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/manifest`: the mini project loads; an unknown key gives an error naming the key; a requirement in °F converts to °C
  exactly; an incompatible unit raises; a claim referring to a missing requirement raises; a `derived_from` cycle raises.

## P2-06 — Producer SDK: decorator, registry, context, code hash
- **Owner:** sonnet · **Depends on:** P2-05 · **Read first:** `docs/03` §9, ADR 0004, `docs/10` §7
- **Files:** `src/reval/sdk/{__init__,producer,registry,context,output}.py`, `src/reval/__init__.py` (export `producer`, `Context`, `ProducerOutput`, `interval_result`, `exact_result`),
  `tests/fixtures/mini_project/mini/__init__.py`, `tests/fixtures/mini_project/mini/producers.py`, `tests/unit/sdk/test_sdk.py`
- **Spec:** exactly `docs/10` §7, except `run_producer` (that's P2-15): `producer(...)` (validates `predictors` ⊆ dependency artifacts), `RegisteredProducer`, `ProducerRegistry`
  (`register`, `get`, `all`, and `load_modules(modules, project_root)`, which recomputes `code_hash`), `DEFAULT_REGISTRY`, `code_hash(fn, project_root)` (D16: the whole top-level
  package's `.py` files plus the qualname), `Context.load` / `param` / `assumption` / `seed` with the D11 rules, `ProducerOutput`, `interval_result`, and `exact_result`.
  Write the four mini producers described in the phase header.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/sdk/test_sdk.py`: loading an undeclared artifact raises `UndeclaredDependencyError`; with only pointer deps, `load` raises and `param` works;
  with column deps, `load` returns only those columns plus the key; editing a **helper module** in the same package changes `code_hash`; a duplicate id raises.

## P2-16 — Snapshot builder
- **Owner:** sonnet · **Depends on:** P2-04, P2-05, P2-06 · **Read first:** `docs/10` §3 (`snapshot_builder.py`), §2 (`Snapshot`), ADR 0005
- **Files:** `src/reval/manifest/snapshot_builder.py`, `tests/unit/manifest/test_snapshot_builder.py`
- **Spec:** `build_snapshot(project_root, manifest, registry, *, git_rev=None) -> Snapshot`: converts units, hashes artifacts in topological order of `derived_from`, collects
  `Producer` metadata from the registry, merges `DEFAULT_POLICIES` with manifest overrides, and computes `Snapshot.id` (D1).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/manifest/test_snapshot_builder.py`: building the mini project twice gives the same id; a different `git_rev` gives the same id;
  editing `/shaft/d_mm` changes the id; the derived `surrogate` hash changes when `data.csv` changes.

## P2-15 — Producer runner
- **Owner:** sonnet · **Depends on:** P2-16 · **Read first:** `docs/10` §7 (`runner.py`), §4.0
- **Files:** `src/reval/sdk/runner.py`, `tests/unit/sdk/test_runner.py`
- **Spec:** `run_producer(registry, producer_id, subject, snapshot, project_root) -> tuple[Evidence, ...]` exactly as `docs/10` §7. Deps use `core.selectors.selector_hash`.
  `scope.assumption_ids = sorted(set(output.scope.assumption_ids) | set(producer.assumes))` (D9). The waiver rules follow D10. A result quantity that isn't in `producer.quantities` → `ProducerError`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/sdk/test_runner.py`: evidence ids are identical across two runs; deps carry the snapshot's selector hashes; `assumes` always ends up in
  `scope.assumption_ids`, even when the producer's scope omits it; a wrong quantity raises.

## P2-07 — Evidence graph (E1)
- **Owner:** sonnet · **Depends on:** P2-15 · **Read first:** `docs/02` §2 E1, `docs/10` §1.5, §4.1
- **Files:** `src/reval/core/graph.py`, `tests/unit/core/test_graph.py`
- **Spec:** `EvidenceGraph.build`, `claim_cone`, `influence`, `evidence_for_claim`, and `to_json(focus)` exactly as `docs/10` §4.1, with NetworkX and the node ids from §1.5.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_graph.py` on the mini project (built with `build_snapshot`, evidence from `run_producer`): `C-SHAFT`'s cone contains
  `field:params#/shaft/d_mm` and not `field:params#/load/scale` or `artifact:data`; the influence of `artifact:data` reaches `artifact:surrogate` → evidence → `claim:C-S1-TEMP`; the output order is deterministic.

## P2-08 — Verdicts (E3 part 1)
- **Owner:** sonnet · **Depends on:** P2-03 · **Read first:** `docs/03` §2, `docs/10` §4.4
- **Files:** `src/reval/core/verdicts.py`, `tests/unit/core/test_verdicts.py`
- **Spec:** `verdict(e: Evidence, req: Requirement) -> tuple[Verdict, tuple[Reason, ...]]` exactly as `docs/10` §4.4. LE: `hi <= L` → PASS, `lo > L` → FAIL, otherwise INCONCLUSIVE.
  GE is symmetric. Waiver → PASS. ML with `in_domain is not True` → INCONCLUSIVE + `OUT_OF_DOMAIN`. Point only (no interval, not exact) → INCONCLUSIVE + `MARGIN_BELOW_UNCERTAINTY`.
  Neither interval nor point → `NO_EVIDENCE`. A unit or quantity mismatch raises `ValueError`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_verdicts.py`: a table-driven test with ≥ 20 rows covering every kind × op × outcome, plus the boundaries
  (`hi == L` → PASS; `lo == L < hi` → INCONCLUSIVE for LE).

## P2-09 — Claim status (E3 part 2) + `assess_all`
- **Owner:** sonnet · **Depends on:** P2-08 · **Read first:** `docs/03` §3, `docs/04` A6, `docs/10` §4.5
- **Files:** `src/reval/core/status.py`, `tests/unit/core/test_status.py`
- **Spec:** `AssessInput`, `assess_claim(claim, snapshot, items, changes=None)`, and `assess_all(snapshot, items, changes=None)`, exactly as `docs/10` §4.5. Status is **history-free**,
  with no `previous` argument. Rule order: VIOLATED → WAIVED → STALE (lost fail) → SUPPORTED → STALE → INCONCLUSIVE. Implement the superseded rule, recorded verdicts,
  brute-force clause matching with distinct evidence, independence via `snapshot.producers[pid].predictors`, the `input_hash` recipe, and sorted outputs.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/core/test_status.py` has a scenario test per rule:
  - FAIL plus PASS → VIOLATED with `CONFLICTING_EVIDENCE`.
  - Medium needs in-domain ML **and** independent physics; ML and physics sharing a predictor → not independent.
  - An INVALIDATED item that was the only support → STALE. An invalidated FAIL with a fresh PASS → STALE (lost fail), not SUPPORTED. A fresh rerun of the same producer supersedes it.
  - Carry-forward PASS → INCONCLUSIVE (current) gives STALE.
  - No evidence → `NO_EVIDENCE`. A matching waiver → WAIVED. A waiver for another claim is ignored.
  - CARRY_FORWARD without `original` → `ValueError`.

## P2-10 — SQL store (document tables)
- **Owner:** sonnet · **Depends on:** P2-03 · **Read first:** ADR 0003, `docs/03` §10, `docs/10` §8
- **Files:** `src/reval/store/{__init__,tables,sql_store,jobs}.py` (**not** `models/`: that name is git-ignored at the root), `tests/unit/store/test_sql_store.py`
- **Spec:** the `Store` protocol, `JobState`, `Job`, `SqlStore`, and `open_store`, exactly as `docs/10` §8, with the tables listed there. Assessments are **append-only batches**:
  `put_assessments` returns a new `seq`, and `get_assessments` defaults to the highest seq (D18). `put_evidence`, `put_snapshot`, and `put_report` are idempotent on identical
  id and body, and **raise** `StoreError` on the same id with a different body. `update_job_state` is the only in-place update. `created_seq` is a store counter, never a clock.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/unit/store`: every object type round-trips on in-memory SQLite; storing assessments twice for one snapshot gives seq 1 and 2, and `get`
  returns seq 2 by default; a duplicate same-body insert is a no-op; a different body raises; `latest_assessed_snapshot` follows the assessment-batch order (so revisiting an old snapshot works);
  job states can move queued → running → succeeded.

## P2-11 — Project service + lock file (no git)
- **Owner:** sonnet · **Depends on:** P2-09, P2-10, P2-15 · **Read first:** `docs/10` §9 (`write_lock`, `read_lock`, `parse_lock`), §10, ADR 0005
- **Files:** `src/reval/services/{__init__,project}.py`, `src/reval/gitio/{__init__,lockfile}.py`, `tests/integration/test_project_service.py`
- **Spec:** `Project.open(root, *, clock=...)`, `snapshot(*, write_lock=False)`, `assess(snapshot=None)`, and `run(producer_id, subject_id)`, per `docs/10` §10. `write_lock`, `read_lock`,
  and `parse_lock` per §9 (git_rev null; the id is verified on read; a missing lock → `LockNotFoundError`). **Phase 2 placeholder freshness** (P3-06 replaces it): an item is FRESH_EXACT
  iff every dep's `version_hash == selector_hash(current, dep.selector)` and the producer code hash is unchanged, and INVALIDATED (`EVIDENCE_INVALIDATED`) otherwise. There's no carry-forward yet.
  Assessments are stored as a new batch.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_project_service.py` on a `tmp_path` copy of the mini project: running every producer and then assessing gives the statuses in
  `EXPECTED.md`; editing `/load/scale` invalidates the temperature evidence but not `shaft_check`; `write_lock` is byte-identical on rerun; a hand-edited lock raises `StoreError` on read.

## P2-17 — CLI: `snapshot` and `status`
- **Owner:** sonnet · **Depends on:** P2-11 · **Read first:** `docs/09` CLI table and exit codes, `docs/10` §11
- **Files:** `src/reval/cli/main.py`, `src/reval/cli/render.py`, `tests/integration/test_cli_status.py`
- **Spec:** `reval snapshot [--write] [--check]` (`--check` exits 1 if the committed lock differs from the live snapshot) and `reval status [--format table|json] [--claim ID]`, each with
  `--project PATH`. Rich tables, plain output when not a TTY, and `--format json` = `canonical_json`. Exit codes per `docs/09`: 0 all accepted, 1 stale/inconclusive, 2 violated, 3 a `RevalError`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_cli_status.py` with `typer.testing.CliRunner` on a `tmp_path` copy of the mini project: `snapshot --write` creates a deterministic lock;
  `snapshot --check` exits 0, and exits 1 after editing a param; `status --format json` parses back into `Assessment` objects; the exit codes are correct; a broken manifest exits 3 with a one-line message.

## P2-18 — CLI: `run --all`
- **Owner:** sonnet · **Depends on:** P2-17 · **Read first:** `docs/09` (`run`), `docs/10` §10
- **Files:** `src/reval/cli/main.py`, `tests/integration/test_cli_run_all.py`
- **Spec:** `reval run --all` runs every producer for every claim subject where `available_for` allows it (the B0 behavior), stores the evidence (append-only), re-assesses, and prints the
  before/after status table. `--plan` and `--only` are added later (P4-10). Keep `--all` working.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_cli_run_all.py`: `snapshot --write`, then `run --all`, then `status` reproduces `EXPECTED.md`; running `run --all` twice adds no duplicate evidence.

## P2-12 — Property tests I1, I2, I4 + core coverage gate
- **Owner:** sonnet · **Depends on:** P2-09, P2-11 · **Read first:** `docs/03` §5
- **Files:** `tests/__init__.py`, `tests/property/__init__.py`, `tests/property/strategies.py` (imported as `tests.property.strategies`; `.` is on the pytest pythonpath), `tests/property/test_invariants_status.py`, `.github/workflows/ci.yml` (add a coverage step)
- **Spec:** Hypothesis strategies for small random projects (≤ 5 artifacts, ≤ 6 claims, ≤ 12 evidence items, random intervals and verdict inputs, and policies drawn from `DEFAULT_POLICIES`),
  built directly as domain objects (no files).
  - **I1:** `assess_all` twice → identical assessments and `input_hash` values. One example is also checked in a subprocess.
  - **I2:** adding or changing items for **other** subjects or quantities never changes a claim's assessment.
  - **I4 (without diff):** turning random items INVALIDATED, or replacing them with CARRY_FORWARD copies whose intervals are widened, with no new evidence added, never moves a claim from non-accepted to accepted. **Supersede exception:** only invalidate an item when no fresh item
    from the same producer exists for the same subject and quantity. A fresh same-producer item counts as new evidence for the item it supersedes (`docs/03` I4).
  - CI: add the step `pytest tests/unit/core tests/property -m "not slow" --cov=reval.core --cov-fail-under=90`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/property` passes under the `ci` profile (200 examples). I3 and I7 come later (P3-10), because they need the diff.

## P2-13 — Motor manifest wiring (non-ML producers)
- **Owner:** sonnet+human-review · **Depends on:** P0-06, P1-08, P1-09, P1-10, P2-18 · **Read first:** `docs/05` §6–7, `docs/03` §8, `docs/10` §12 (`producers.py`)
- **Files:** `examples/motor_thermal/reval.yaml`, `examples/motor_thermal/motor/producers.py`, `tests/integration/test_motor_manifest.py`
- **Spec:**
  - Declare these artifacts:
    - `measures` (dataset, key `[profile_id]`) and `splits` (params);
    - `drive_map` (model, `derived_from: [measures, splits]`);
    - `tpm_<m>` / `tsw_<m>` for m ∈ {ridge, hgb, mlp} (model, `derived_from: [measures, splits]`);
    - `lptn` (params, `derived_from: [measures, splits]`), `cooling` (params, `params/cooling.yaml`), and `limits` (params).
  - Declare the assumptions, requirements from `limits.yaml` (pm high, sw medium, current medium, shaft low), and subjects via `subjects_file: subjects.yaml`.
  - Claims: pm and sw for every subject, plus `C-SHAFT` and current-limit claims.
  - Producers with the binding names:
    - `lptn_sim` (PHYSICS_SIM, fidelity 2, cost 5, predictors `["lptn"]`, depends on the pointer selectors `lptn#/R`, `lptn#/C`, `lptn#/loss` (never the whole `lptn`, so P3-07's tolerances can apply), `drive_map`, and `cooling#/flow_scale`);
    - `bench_measure` (MEASUREMENT, fidelity 3, cost 100, depends on `measures[pm,stator_winding]` and `cooling#/flow_scale`, `available_for` = recorded test cycles);
    - `shaft_check` (ANALYTIC);
    - `current_limit_check` (ANALYTIC, **fidelity 3**, through the drive map; fidelity 3 is needed to satisfy the medium policy's `[analytic{min_fidelity: 3}]` clause).
  - The ML producers come in P4-03. Declare every dependency at field or column level where possible.
- **Acceptance:** `.venv/Scripts/python -m pytest -m data tests/integration/test_motor_manifest.py` runs `reval snapshot --write`, `reval run --all`, and `reval status` in a temp copy and checks that
  every claim has an assessment. Without data it is skipped. NEEDS HUMAN: the claim statuses make sense.
