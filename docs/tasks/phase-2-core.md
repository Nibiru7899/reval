# Phase 2 — Core engine (roadmap weeks 7–10)

**Binding spec:** `docs/10-interfaces.md` (exact module paths, class fields, and signatures). `docs/03-domain-model.md` is the semantic contract.
If the two disagree, stop and log it in `docs/log/questions.md`. Conventions: see the header of `phase-0-foundations.md`.
All `src/reval/domain` and `src/reval/core` code passes `mypy --strict`.

---

## P2-01 — Domain base, quantities, canonical JSON, hashing utilities
- **Owner:** sonnet · **Depends on:** P0-01 · **Read first:** `10-interfaces.md` §1–2, ADR 0001
- **Files:** `src/reval/domain/base.py` (`Frozen` base: `frozen=True, extra="forbid"`), `src/reval/domain/quantities.py` (`Quantity`, `Interval` with `lo <= hi` validator, `widen(delta)`, `width`),
  `src/reval/core/canonical.py` (`canonical_json(obj) -> bytes`, `sha256_hex(b) -> str`, `content_id(model, exclude={"id"}) -> str`), tests in `tests/unit/core/test_canonical.py`.
- **Spec:** canonical JSON = `json.dumps(model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded UTF-8.
  Floats: reject NaN/inf (raise `ValueError`). Tuples serialize as lists.
- **Acceptance:** tests: key-order independence; identical bytes across two constructions; `Interval(lo=2, hi=1)` raises; `widen(-1)` raises; NaN rejected.

## P2-02 — Domain entities: artifacts, engineering, evidence, policies
- **Owner:** sonnet · **Depends on:** P2-01 · **Read first:** `docs/03` §1–3, `10-interfaces.md` §3
- **Files:** `src/reval/domain/{artifacts,engineering,evidence,policies}.py`, update `src/reval/domain/__init__.py` exports, tests in `tests/unit/domain/`.
- **Spec:** implement exactly the fields in `10-interfaces.md` §3, including `DependencyRef.parse()` for the selector syntax (`id`, `id#/json/pointer`, `id[col1,col2]`)
  and `DEFAULT_POLICIES` (low/medium/high as in `docs/03` §3). Validators: an `Assumption` has exactly one of `bounds` / `value`; `Tolerance.sensitivity >= 0`,
  `safety_factor >= 1`; `Evidence.id == content_id(evidence)` is checked by `Evidence.create(...)` (a factory that computes the id).
- **Acceptance:** round-trip `model_validate(model_dump())` for every entity; selector parse table test (≥ 8 cases incl. errors); `DEFAULT_POLICIES["high"]` has 2 clauses.

## P2-03 — Snapshot, changes, assessment, plan models
- **Owner:** sonnet · **Depends on:** P2-02 · **Read first:** `10-interfaces.md` §3 (snapshot/changes/assessment/plan)
- **Files:** `src/reval/domain/{snapshot,changes,assessment,plan}.py`, tests.
- **Spec:** `Snapshot.create(...)` computes `id = content_id(...)` (ADR 0005). `Snapshot.selector_hash(ref: str) -> str | None` returns the field hash, or the whole-artifact hash for `*`.
  `ChangeKind`, `Change`, `ChangeSet`, `Reason`, `EvidenceUse`, `Assessment`, `Obligation`, `CandidateRun`, `PlannedRun`, `RevalidationPlan` per spec.
- **Acceptance:** snapshot id stable under dict insertion order; `selector_hash` cases for params field, dataset column, and whole artifact; JSON round-trip of every model.

## P2-04 — Hashers (`reval.hashing`)
- **Owner:** sonnet · **Depends on:** P2-03, P0-01 · **Read first:** `docs/04` A1, `10-interfaces.md` (hashing section)
- **Files:** `src/reval/hashing/{__init__,base,file,yaml_fields,dataframe,model}.py`, tests in `tests/unit/hashing/` with tmp files.
- **Spec:** `hash_artifact(artifact, root, upstream: Mapping[str, ArtifactVersion]) -> ArtifactVersion`, dispatched by `artifact.hasher`.
  - `file`: SHA-256 of bytes. A missing file gives `content_hash="missing"`.
  - `yaml-fields`: JSON-pointer per leaf (`/a/b/0`). `field_hashes[ptr] = sha256(canonical json of value)`. `field_values[ptr]` for scalar leaves.
  - `dataframe`: parquet or csv. Key group column = `artifact.key[0]`. `field_hashes["c=<col>"]` and `["g=<group>/c=<col>"]` from `pd.util.hash_pandas_object(series, index=False)`.
    `row_groups[group] = RowGroupInfo(n_rows, bbox={numeric col: (min, max)})`.
  - `model`: `content_hash = sha256(file_sha + "|" + "|".join(sorted upstream content hashes of derived_from))`, a constructive trace: retraining is
    not needed for the hash to change when upstream data changes.
- **Acceptance:** tests: editing one YAML leaf changes exactly one field hash; modifying one profile's `pm` changes only `g=<p>/c=pm` and `c=pm`;
  row order within a group irrelevant? **No:** order matters. Test that it does and document why (time series). An upstream change alters the model hash with the file unchanged.

## P2-05 — Manifest schema + loader with units
- **Owner:** sonnet · **Depends on:** P2-03 · **Read first:** `docs/03` §6, `10-interfaces.md` (manifest section)
- **Files:** `src/reval/manifest/{__init__,schema,loader,units}.py`, `tests/unit/manifest/`, fixture `tests/fixtures/mini_project/` (a tiny project: 1 yaml params artifact, 1 csv dataset, 2 requirements, 2 subjects, 3 claims, a producers module with 2 trivial producers).
- **Spec:** `load_manifest(path) -> Manifest` (pydantic, `extra="forbid"`, line-numbered error messages where possible); `quantities:` map of canonical units;
  `units.to_canonical(value, unit, canonical_unit)` via pint (absolute °C vs. K delta handled: limits are absolute and use `Quantity(v, unit).to(canonical)`).
  `subjects:` may be inline or `subjects_file: subjects.yaml`.
- **Acceptance:** the mini project loads; unknown key → error naming the key; a requirement in °F converts to °C exactly; a requirement with a unit incompatible with its quantity → error.

## P2-06 — Producer SDK + registry + runner
- **Owner:** sonnet · **Depends on:** P2-04, P2-05 · **Read first:** `docs/03` §7, ADR 0004, `10-interfaces.md` (sdk section)
- **Files:** `src/reval/sdk/{__init__,producer,registry,context,output,runner}.py`, export `reval.producer`, `reval.Context`, `reval.Subject` from `src/reval/__init__.py`. Tests in `tests/unit/sdk/`.
- **Spec:** the `@producer(...)` decorator registers into the default `ProducerRegistry`. `code_hash = sha256(module file bytes + qualname)`.
  `ProducerRegistry.load_module("motor.producers", project_root)` inserts `project_root` into `sys.path` (restored afterwards) and imports.
  `Context.load(artifact_id)` / `Context.param("cooling#/coolant/flow_lpm")` raise `UndeclaredDependencyError` if not in `depends_on`.
  The runner `run_producer(registry, producer_id, subject, snapshot, project_root, seed=0) -> list[Evidence]` wraps `ProducerOutput` into `Evidence.create(...)` with
  deps = declared selectors at their current snapshot hashes, provenance (code hash, snapshot id, python + package versions of numpy/scipy/sklearn when importable, seed).
- **Acceptance:** an undeclared load raises; editing the producer module changes the code hash; evidence ids are deterministic across two runs; deps carry the right hashes.

## P2-07 — Evidence graph (E1)
- **Owner:** sonnet · **Depends on:** P2-03 · **Read first:** `docs/02` §2 E1, `10-interfaces.md` (core.graph)
- **Files:** `src/reval/core/graph.py`, `tests/unit/core/test_graph.py`
- **Spec:** `EvidenceGraph.build(snapshot, evidence)`: node ids `artifact:`, `field:`, `assumption:`, `requirement:`, `subject:`, `claim:`, `evidence:`, `producer:`. Edges point dependency → dependent.
  Artifacts' `derived_from` edges go artifact → artifact. `claim_cone(claim_id)` = ancestors; `influence(node_id)` = descendants;
  `evidence_for_claim(claim_id)` = evidence with the same subject_id and `result.quantity == requirement.quantity`, sorted by id.
- **Acceptance:** tests on the mini project: the shaft claim's cone excludes the thermal params; influence of a dataset reaches models → evidence → claims; deterministic ordering.

## P2-08 — Verdicts (E3 part 1)
- **Owner:** sonnet · **Depends on:** P2-02 · **Read first:** `docs/03` §2 (table)
- **Files:** `src/reval/core/verdicts.py`, `tests/unit/core/test_verdicts.py`
- **Spec:** `verdict(e: Evidence, req: Requirement, interval: Interval | None = None) -> tuple[Verdict, tuple[Reason, ...]]`, exactly per the table, for both `<=` and `>=`.
  Boundary: `hi == L` → PASS; `lo == L` with `op "<="` → INCONCLUSIVE unless `hi <= L`. ML not in domain (False or None) → INCONCLUSIVE + `OUT_OF_DOMAIN`. Waiver → PASS.
  A unit mismatch raises `ValueError`.
- **Acceptance:** a table-driven test with ≥ 20 rows covering every kind × op × pass/fail/inconclusive, plus the boundary cases.

## P2-09 — Claim status (E3 part 2) + `assess_all`
- **Owner:** sonnet · **Depends on:** P2-07, P2-08 · **Read first:** `docs/03` §3, `docs/04` A6, `10-interfaces.md` (core.status)
- **Files:** `src/reval/core/status.py`, `tests/unit/core/test_status.py`
- **Spec:** `assess_claim(claim, snapshot, items: Sequence[tuple[Evidence, FreshnessClass]], previous: Assessment | None, changes: ChangeSet | None = None) -> Assessment`
  implementing rule order VIOLATED → WAIVED → SUPPORTED → STALE → INCONCLUSIVE. Only fresh classes are eligible (`INVALIDATED` items are only used to detect STALE).
  Clause matching: brute force over distinct evidence assignments, with independence per `docs/03` §3. `input_hash` per `10-interfaces.md`.
  `assess_all(snapshot, evidence_items, previous) -> dict[claim_id, Assessment]` sorted by claim id.
  Until P3 lands, freshness can be passed in as `FRESH_EXACT` by tests.
- **Acceptance:** scenario tests: fail dominates pass (`CONFLICTING_EVIDENCE`); the medium policy needs both ML-in-domain and physics; previously supported + invalidated → STALE;
  no evidence → INCONCLUSIVE + `NO_EVIDENCE`; a waiver → WAIVED.

## P2-10 — SQL store (document tables)
- **Owner:** sonnet · **Depends on:** P2-03, P0-01 · **Read first:** ADR 0003, `docs/03` §8, `10-interfaces.md` (store section)
- **Files:** `src/reval/store/{__init__,tables,sql_store}.py` (**not** `models/`: that dir name is git-ignored), `tests/unit/store/test_sql_store.py`
- **Spec:** SQLAlchemy 2 Core or ORM tables per `docs/03` §8. `SqlStore(url)`. `metadata.create_all` on open. Methods per `10-interfaces.md`.
  `open_store(project_root)` → `sqlite:///<root>/.reval/reval.db` unless `REVAL_DATABASE_URL` is set. Put methods for evidence/assessments are idempotent on identical id, and **raise** on the same id with a different body (append-only).
- **Acceptance:** round-trip each object type on in-memory SQLite; the duplicate-same-body insert is a no-op; a different body raises; `latest_snapshot` follows insertion order (`created_seq`).

## P2-11 — Project service + `reval status` / `reval snapshot`
- **Owner:** sonnet · **Depends on:** P2-04…P2-10 · **Read first:** `docs/09` CLI table, ADR 0005, `10-interfaces.md` (services, cli)
- **Files:** `src/reval/services/project.py`, `src/reval/cli/main.py` (+ `cli/render.py`), `src/reval/gitio/lockfile.py` (write/read `reval.lock.json` only, no git yet), tests in `tests/integration/test_cli_status.py`.
- **Spec:** `Project.open(root)`, `.snapshot()`, `.write_lock(snapshot)`, `.assess(snapshot)` (Phase 2: treats all stored evidence whose deps all match current hashes as FRESH_EXACT and everything else as INVALIDATED; P3 replaces this).
  CLI: `reval snapshot [--write] [--check]`, `reval status [--format table|json] [--claim ID]`, `reval run --all` (runs every producer for every claim subject: B0 behavior, needed to get evidence at all).
  Exit codes per `docs/09`. Table output uses `rich` (already a dependency), and output is plain when not a TTY or with `--format json`.
- **Acceptance:** an integration test on a temp copy of `tests/fixtures/mini_project`: `snapshot --write` creates a deterministic lock (byte-identical on rerun); `run --all` then `status` shows SUPPORTED/INCONCLUSIVE as designed;
  `status --format json` validates against `Assessment`; exit codes are correct.

## P2-12 — Property tests I1, I2, I4, I7
- **Owner:** sonnet · **Depends on:** P2-09, P2-11 · **Read first:** `docs/03` §5
- **Files:** `tests/property/{strategies,test_invariants_status}.py`
- **Spec:** Hypothesis strategies for random small projects (≤ 5 artifacts, ≤ 6 claims, ≤ 12 evidence items, random intervals/verdict inputs, random policies from DEFAULT_POLICIES).
  I1: assess twice (and in a subprocess for one example) → identical assessments and hashes. I2: perturb an artifact outside a claim's cone → the claim's status is unchanged.
  I4: re-assess with a random change set but no new evidence → no claim moves from non-accepted to accepted unless a `REQUIREMENT_CHANGED` loosened its limit. I7: diff(S,S) is empty and assess is unchanged.
- **Acceptance:** `pytest tests/property` passes with `max_examples=200` (profile `ci`) and 2000 locally (profile `thorough`, documented in conftest).

## P2-13 — Motor manifest wiring
- **Owner:** sonnet+human-review · **Depends on:** P2-11, P1-12 · **Read first:** `docs/05` §6–7, `docs/03` §6
- **Files:** `examples/motor_thermal/reval.yaml`, `examples/motor_thermal/motor/producers.py`
- **Spec:** declare artifacts (measures, splits, drive_map, tpm/tsw models, lptn params, cooling params, limits), assumptions, requirements from `limits.yaml` values,
  subjects via `subjects_file`, claims (pm + sw for every subject, plus `C-SHAFT` and current-limit claims), and producers `predict_peak_ridge` (ml_prediction, cost 1),
  `lptn_sim` (physics_sim, fidelity 2, cost 5), `bench_measure` (measurement, fidelity 3, cost 100, `available_for` = recorded subjects only), `shaft_check`, `current_limit_check`.
  Declare every dependency at **field level** where possible.
- **Acceptance:** `cd examples/motor_thermal && reval snapshot --write && reval run --all && reval status` works with data present (`@pytest.mark.data` integration test). A human checks that the claim statuses make sense.
