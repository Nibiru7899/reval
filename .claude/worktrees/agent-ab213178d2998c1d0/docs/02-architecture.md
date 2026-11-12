# 02 — Architecture

## 1. Layering

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Interfaces     CLI (Typer)   ·   REST API (FastAPI)   ·   Web UI (React) │
│                GitHub Action (wraps CLI)                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ Application    ProjectService · AssessmentService · PlanService ·        │
│                JobRunner · ReportBuilder                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ Core engines (pure, deterministic, no I/O)                               │
│   E1 Evidence graph   E2 Change impact   E3 Validity   E4 Planner        │
├──────────────────────────────────────────────────────────────────────────┤
│ Domain model   Artifact · Version · Assumption · Requirement · Claim ·   │
│                Evidence · Producer · Policy · Snapshot · ChangeSet       │
├──────────────────────────────────────────────────────────────────────────┤
│ Adapters       Manifest loader (YAML) · Hashers (file, field, dataframe) │
│                Store (SQLite / PostgreSQL) · Git reader · Producer SDK   │
└──────────────────────────────────────────────────────────────────────────┘
        ▲ used by
┌────────────────────────────┐   ┌─────────────────────────────────────┐
│ examples/motor_thermal     │   │ bench/ (ReValBench)                 │
│ data, models, LPTN,        │   │ scenario generator, oracles,        │
│ optimizer, producers       │   │ baselines, metrics, experiments     │
└────────────────────────────┘   └─────────────────────────────────────┘
```

**Hard rule:** `reval.core` has no I/O, no network, no randomness without an explicit seed, no wall-clock reads, and no LLM calls.
It takes immutable domain objects in and returns immutable results out. This is what makes assessments reproducible
and property-testable.

## 2. The four engines

### E1 — Evidence graph
- A typed DAG with node types `Artifact`, `Assumption`, `Requirement`, `Evidence`, `Claim`, `Producer`.
- Edges: `DEPENDS_ON(evidence → artifact-field)`, `ASSUMES(evidence → assumption)`, `SUPPORTS / REFUTES(evidence → claim)`, `CHECKS(claim → requirement)`, `PRODUCED_BY(evidence → producer)`.
- Built in memory with NetworkX from a snapshot. Persisted relationally.
- Queries: dependency cone of a claim, influence cone of an artifact field, justification tree of a claim.

### E2 — Change impact
- Input: snapshots *S*, *S′* (content-addressed). Output: a `ChangeSet` (typed, field-level diffs) and the set of evidence whose freshness is in question.
- Three stages, cheapest first:
  1. **Structural:** hash comparison at field granularity (JSON-pointer for params, column + row-range for datasets, model hash).
  2. **Scope:** does the change intersect the evidence's declared validity scope? (Example: new data rows outside the claim's duty-cycle envelope don't touch an evidence item whose scope is that envelope.)
  3. **Tolerance:** is the magnitude of the change provably below the evidence's declared sensitivity bound?
- Unknown change kinds, or evidence with no declared scope or tolerance, **fail closed** (treated as invalidated). So do subject changes, upstream changes of derived
  artifacts (hash folding, D3), and whole-artifact dependencies on a changed artifact. Exact rules: `10-interfaces.md` §4.3.

### E3 — Validity
- For each claim, evaluates its evidence policy against the *fresh* evidence available. It is history-free: the status depends only on the current snapshot and the
  evidence with its freshness classes, never on earlier assessments (D4).
- Evidence-level checks: applicability domain (is the subject inside the model's validated envelope?), calibrated
  interval vs. requirement limit (conformal), agreement between independent sources, assumption satisfaction.
- Produces an `Assessment`: status, reasons (machine-readable codes + human text), the evidence used, and a content hash of all inputs.

### E4 — Planner
- Converts every non-decided claim into *obligations*, generates candidate producer runs, and solves an ILP with OR-Tools CP-SAT
  (min-cost, or max-restored-under-budget).
- Greedy and "rerun-all" planners are implemented next to it as baselines.
- Output: `RevalidationPlan` (ordered runs, cost, which obligations each run discharges, expected post-plan statuses).

See [04-algorithms.md](04-algorithms.md) for the formal definitions.

## 3. Key design decisions (summary — full ADRs in `docs/adr/`)

| Decision | Choice | Why |
|---|---|---|
| Source of truth for metadata | `reval.yaml` manifest + `@reval.producer` decorators in the user's repo | Explicit, reviewable in PRs, versioned with git |
| Snapshot identity | `content_id` of the canonical snapshot JSON, excluding `id` and `git_rev` (D1) | Same project state ⇒ same snapshot id, on any machine and at any commit |
| Git integration | The snapshot is committed as `reval.lock.json` (ADR 0005), so `reval diff HEAD~1 HEAD` reads both locks via `git show` | The "CI for evidence" story. Works even though data and models are git-ignored. |
| Store | SQLAlchemy "document tables" (indexed key columns + a JSON body). SQLite by default, PostgreSQL via URL (ADR 0003). | Local-first. Postgres for multi-user and the demo deployment. Domain objects stay the single schema. |
| Evidence results | Stored with full provenance: producer id + code hash, input version hashes, env (package versions), seed, cost, wall time | Needed for reproducibility and the "reuse" decision |
| Job execution | In-process worker with a `jobs` table (no Celery/Redis) | Fewer moving parts. Bench runs are simulated in the benchmark anyway. |
| Units | `pint` at the manifest boundary; canonical units stored with every quantity | Prevents °C/K and absolute/difference mix-ups, a classic thermal bug |
| LLM | Optional, last, explanation-only, behind a feature flag | The deterministic core certifies; the LLM never does |
| Frontend | Vite + React + TypeScript, `@xyflow/react` for graphs, Plotly for envelopes | A local SPA served by FastAPI. Next.js SSR isn't needed. |

## 4. Repository layout (target)

```
ReVal/
├── AGENTS.md                 # rules for AI coding agents (and humans)
├── README.md
├── pyproject.toml            # single Python project, src layout
├── src/reval/
│   ├── core/                 # pure engines: canonical.py selectors.py graph.py diff.py freshness.py verdicts.py status.py planner.py
│   ├── uq/                   # conformal + applicability-domain helpers for producers (pure numpy/scipy)
│   ├── errors.py             # all ReVal exception types
│   ├── domain/               # pydantic models: artifacts, evidence, claims, policies, snapshot
│   ├── manifest/             # reval.yaml schema + loader + unit handling
│   ├── hashing/              # file/field/dataframe/model hashers
│   ├── sdk/                  # @producer decorator, ProducerContext, Evidence builders
│   ├── store/                # SQLAlchemy models, repositories, migrations (alembic)
│   ├── gitio/                # read snapshots at git revisions
│   ├── services/             # application layer
│   ├── api/                  # FastAPI app
│   ├── cli/                  # Typer app (entry point `reval`)
│   └── report/               # HTML/Markdown/JSON report rendering
├── examples/motor_thermal/   # reference project (has its own reval.yaml)
│   ├── reval.yaml
│   ├── motor/                # data loading, features, models, lptn, optimizer, producers
│   └── scripts/              # download_data.py, train.py, calibrate_lptn.py
├── bench/                    # ReValBench: scenarios/, oracles/, baselines/, run.py, analysis/
├── web/                      # Vite React app
├── tests/                    # unit, property (hypothesis), integration, golden
└── docs/                     # this plan
```

## 5. Data flow for one change (example)

1. The engineer edits `params/cooling.yaml: flow_scale 1.0 → 0.95` (5 % less coolant flow) and commits the code and the regenerated `reval.lock.json`.
2. `reval diff HEAD~1 HEAD` reads both locks. E2 reports `FIELD_CHANGED(cooling#/flow_scale, 1.0 → 0.95, Δ = −0.05)`.
3. Relevance: `lptn_sim` evidence declares `cooling#/flow_scale` with a tolerance (the LPTN maps it to `R_ic ∝ flow_scale^-0.8`). ML evidence declares it **without** a
   tolerance, because the training data contains no flow variation.
4. Excuse: for `lptn_sim`, the raw sensitivity is ~6 K per unit and κ = 1.5, so the inflation is 1.5 · 6 · 0.05 ≈ 0.45 K → CARRY_FORWARD. On DC-02 (15 K margin) the widened
   interval still passes. On DC-07 (0.3 K margin) it becomes INCONCLUSIVE. The ML evidence is INVALIDATED (`MISSING_TOLERANCE`) everywhere.
5. E3 under the *high* policy: DC-02 has a fresh measurement → **Supported**. DC-07 → **Stale** (support lost to the change). The shaft claim isn't in the cone and stays **Supported**.
6. E4: the cheapest restoration of DC-07 is one ML re-evaluation under the new state (cost 1) plus one LPTN re-simulation (cost 5), using the clause
   "physics + independent in-domain ML". It recommends **no** bench run (cost 100).
7. `reval run --plan <id>` executes the producers, stores the new evidence append-only, and re-assesses. The report records everything with hashes.

(The numbers are illustrative.)
