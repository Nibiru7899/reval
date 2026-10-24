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
- Unknown change kinds, or evidence with no declared scope or tolerance, **fail closed** (treated as invalidated).

### E3 — Validity
- For each claim, evaluates its evidence policy against the *fresh* evidence available.
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
| Snapshot identity | Merkle hash over all artifact-field hashes and manifest | Same project state ⇒ same snapshot id, on any machine |
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
│   ├── core/                 # pure engines: graph.py impact.py validity.py planner.py status.py
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

1. The engineer edits `params/cooling.yaml: coolant.flow_lpm 8.0 → 6.5` and commits.
2. `reval diff HEAD~1 HEAD` builds both snapshots. E2 reports `FieldChanged(params/cooling.yaml#/coolant/flow_lpm, 8.0→6.5)`.
3. Influence cone: the LPTN parameter `R_coolant` is derived from `flow_lpm`. Evidence `lptn_sim(DC-07)` and `bench(DC-03)` depend on it.
   ML evidence trained on data recorded at 8.0 L/min has `flow_lpm` in its assumption scope.
4. Tolerance check: the declared sensitivity of peak T_pm to flow is ~1.9 K per L/min. Δ = 1.5 L/min ⇒ up to ~2.9 K, which exceeds the
   2 K margin on DC-07 ⇒ stale. DC-02 has a 15 K margin ⇒ that evidence stays fresh.
5. E3: DC-07 → **Stale**. DC-02 → **Supported**. The mechanical-dimension claim M-01 isn't in the cone and stays **Supported**.
6. E4: the cheapest restoration of DC-07 under the *high-criticality* policy is one LPTN re-simulation (cost 3), plus ML re-evaluation
   with the new assumption (cost 1). It recommends **no** bench run, because the policy alternative "ML-in-domain + independent physics agreement" is satisfiable.
7. `reval run --plan latest` executes the producers, stores the new evidence, and re-assesses. The report records everything with hashes.

(The numbers are illustrative.)
