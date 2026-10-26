# Phase 6 — API, web workspace, CI integration (roadmap weeks 24–27, milestone M6)

**Read first for every task:** `AGENTS.md`, `docs/09-api-and-ui.md`, `docs/10-interfaces.md` §8, §11, ADR 0003.
**Gate:** Phase 6 starts only after the M5 DoD (P5-16), so P6-01 depends on it. If M5 isn't met by week 23, do only the static HTML report (`reval report --html`, already done in P4-13).
The GitHub Action (P6-13) is cut line 4 and is dropped before the static HTML report (cut line 5). See the cut lines in `docs/07-roadmap.md`.
**Phase goal (M6 DoD):** the workspace runs locally on the motor example (`reval serve`, or `docker compose up`), and the demo PR shows the GitHub Action comment.
**API scope (D27):** single project. The routes keep `/projects/{p}`, but only `p = "default"` exists, with its root from `REVAL_PROJECT_ROOT`. Any other `p` → 404.
**Frontend stack:** Vite + React 18 + TypeScript (strict), TanStack Query, `openapi-typescript` + `openapi-fetch` (a generated client), `@xyflow/react`, `plotly.js-dist-min`, Vitest + Testing Library + `vitest-axe`.
Pin exact versions in `package.json`. Conventions: see the header of `phase-0-foundations.md`. Tests use the mini project fixture.

---

## P6-01 — FastAPI app skeleton + `reval serve`
- **Owner:** sonnet · **Depends on:** P4-15, P5-16 · **Read first:** `docs/09` (REST API), `docs/10` §11
- **Files:** `src/reval/api/{__init__,app,deps,settings}.py`, `src/reval/cli/main.py` (`serve`), `tests/integration/api/test_health.py`
- **Spec:** `create_app(settings: ApiSettings) -> FastAPI` mounts the API at `/api/v1`. `GET /api/v1/health` → `{status, version}`. A dependency injects a `Project` opened from `REVAL_PROJECT_ROOT`.
  Response models are **imported from `reval.domain` / `reval.report`**, never redefined. `reval serve [--host] [--port]` launches uvicorn. The `server` extra is required, and a clear
  `MissingExtraError("server")` is raised without it.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/api/test_health.py`: the `TestClient` health check passes; `GET /api/v1/openapi.json` parses as OpenAPI 3.

## P6-02 — Read endpoints: projects, snapshots, claims, evidence, diff, graph
- **Owner:** sonnet · **Depends on:** P6-01 · **Read first:** `docs/09` (route list)
- **Files:** `src/reval/api/routes/{__init__,projects,snapshots,claims,evidence,diff,graph}.py`, `tests/integration/api/test_read_routes.py`
- **Spec:** exactly the GET routes in `docs/09`, plus `POST /projects/default/snapshots`. `graph` returns `EvidenceGraph.to_json(focus)` with an optional `status` per claim node.
  Lists take `?limit&offset`. `p != "default"` → 404.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/api/test_read_routes.py` on the mini project: every route is tested, including 404 for unknown ids and for `p=other`.

## P6-03 — Plans, jobs, SSE
- **Owner:** sonnet · **Depends on:** P6-02 · **Read first:** `docs/09`, `docs/10` §8 (jobs)
- **Files:** `src/reval/api/routes/{plans,jobs}.py`, `tests/integration/api/test_plans_jobs.py`
- **Spec:** `POST /projects/default/plans` (body: snapshot, budget?, planner) → plan. `POST /projects/default/plans/{id}/execute` → job id; the job runs in a background thread via `services.jobs`.
  `GET /jobs/{id}` and `GET /jobs/{id}/events` (SSE events: `state`, `progress`, `done`).
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/api/test_plans_jobs.py`: execute a plan on the mini project and poll until `succeeded`; the SSE test reads at least one event.
- **Pitfalls:** SQLite with threads needs one engine with `check_same_thread=False` and a session per request or job.

## P6-04 — Report endpoints
- **Owner:** sonnet · **Depends on:** P6-02, P4-13 · **Read first:** `docs/09` (report format)
- **Files:** `src/reval/api/routes/reports.py`, `tests/integration/api/test_reports.py`
- **Spec:** `POST /projects/default/reports` (body: snapshot) builds and stores a report (`put_report`). `GET /projects/default/reports/{id}?format=json|html|md`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/api/test_reports.py`: all three formats are covered; the HTML contains the disclaimer; the same state gives the same report id twice.

## P6-05 — Alembic migrations, `reval db upgrade`, PostgreSQL CI
- **Owner:** sonnet · **Depends on:** P6-01 · **Read first:** ADR 0003, `docs/10` §8 (tables)
- **Files:** `src/reval/store/migrations/` (env + initial revision), `alembic.ini`, `src/reval/cli/main.py` (`db upgrade`), `.github/workflows/ci.yml` (a `postgres:16` service job with `.[dev,motor,server,postgres]`), `tests/integration/test_migrations.py`
- **Spec:** the initial migration matches `docs/10` §8, including `assessments.seq` and `jobs`. `reval db upgrade` applies the migrations to `REVAL_DATABASE_URL`. `SqlStore` keeps `create_all` for SQLite dev use.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_migrations.py`: upgrade on a fresh SQLite file, then `alembic check` reports no drift. The CI Postgres job runs the integration tests against Postgres. (This is cut line 2 in `docs/07`: drop the Postgres job if behind.)

## P6-06 — Web scaffold, generated client, `reval api-schema`
- **Owner:** sonnet · **Depends on:** P6-02 · **Read first:** `docs/09`
- **Files:** `web/` (Vite React TS: `package.json`, `vite.config.ts`, `tsconfig.json`, `src/main.tsx`, `src/App.tsx`, `src/api/client.ts`, `src/api/schema.d.ts` generated), `src/reval/cli/main.py`
  (`api-schema`), `src/reval/api/app.py` (serve `web/dist` at `/`), `.github/workflows/ci.yml` (a web build job), `tests/integration/test_cli_api_schema.py`
- **Spec:** `reval api-schema --out openapi.json` writes the OpenAPI schema. `npm --prefix web run gen:api` runs `openapi-typescript ../openapi.json -o src/api/schema.d.ts`.
  The app shell has a left nav (Claims, Changes, Graph, Planner, Reports), a snapshot selector, and light/dark themes via CSS variables.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_cli_api_schema.py`; `npm --prefix web run build` and `npm --prefix web test` pass; CI builds the web app.
- **Pitfalls:** never hand-write API types. Regenerate them.

## P6-07 — Claim board page
- **Owner:** sonnet · **Depends on:** P6-06 · **Read first:** `docs/09` UI page 1
- **Files:** `web/src/pages/ClaimBoard.tsx`, `web/src/components/StatusBadge.tsx`, `web/src/pages/ClaimBoard.test.tsx`
- **Spec:** a grid of claims × recent snapshots. Each cell shows a status icon **and** label, never color alone. Filters: requirement, criticality, status. A headline count: "N claims need revalidation since <rev>". Clicking a cell opens the claim detail.
- **Acceptance:** `npm --prefix web test -- ClaimBoard` passes a render test with a mocked client and a `vitest-axe` check with no violations.

## P6-08 — Claim detail: justification tree + envelope plot
- **Owner:** sonnet · **Depends on:** P6-07 · **Read first:** `docs/09` UI page 2
- **Files:** `web/src/pages/ClaimDetail.tsx`, `web/src/components/{JustificationTree,EnvelopePlot,IntervalChart}.tsx`, `web/src/pages/ClaimDetail.test.tsx`, `src/reval/api/routes/claims.py`
  (add `GET /projects/default/claims/{c}/envelope`), `docs/09-api-and-ui.md` (document the route), `tests/integration/api/test_envelope.py`
- **Spec:**
  - Status and reasons, plus a collapsible justification tree (clause → evidence → deps).
  - The envelope plot over two selectable features: the AD box from `domain_report` and downsampled training points (from the new endpoint), with the subject trajectory overlaid and the out-of-domain segment highlighted.
  - An interval-vs-limit chart per evidence item.
- **Acceptance:** `npm --prefix web test -- ClaimDetail` and `.venv/Scripts/python -m pytest tests/integration/api/test_envelope.py` pass. NEEDS HUMAN: a visual check in the browser against the motor example.

## P6-09 — Change timeline
- **Owner:** sonnet · **Depends on:** P6-06 · **Read first:** `docs/09` UI page 3
- **Files:** `web/src/pages/Timeline.tsx`, `web/src/pages/Timeline.test.tsx`
- **Spec:** a list of snapshots (git rev, change counts). Clicking one shows its change set grouped by artifact. Selecting a change highlights the affected claims (via `/graph?focus=`).
- **Acceptance:** `npm --prefix web test -- Timeline` passes render tests with fixtures.

## P6-10 — Graph explorer
- **Owner:** sonnet · **Depends on:** P6-06 · **Read first:** `docs/09` UI page 4
- **Files:** `web/src/pages/GraphExplorer.tsx`, `web/src/lib/layout.ts` (dagre), `web/src/pages/GraphExplorer.test.tsx`
- **Spec:** `@xyflow/react` with a dagre layout, collapsed to claim level by default and expanding on click. Cone highlighting for the selected node. Node shapes per type, with a status badge.
- **Acceptance:** `npm --prefix web test -- GraphExplorer`: the layout of a 500-node fixture finishes and returns 500 positioned nodes; collapsed mode shows only claim-level nodes. NEEDS HUMAN: interaction feels responsive in the browser.

## P6-11 — Planner page
- **Owner:** sonnet · **Depends on:** P6-03, P6-06 · **Read first:** `docs/09` UI page 5
- **Files:** `web/src/pages/Planner.tsx`, `web/src/pages/Planner.test.tsx`
- **Spec:**
  - An obligations table, a planner selector, and a budget slider (debounced re-solve via `POST /plans`).
  - A plan table (run, producer, subject, cost, discharges) that shows `unrestorable` and `deferred` separately.
  - An "Execute" button: job progress via SSE, then a before/after status table.
- **Acceptance:** `npm --prefix web test -- Planner` passes render and interaction tests with a mocked client.

## P6-12 — Report view
- **Owner:** sonnet · **Depends on:** P6-04, P6-06 · **Read first:** `docs/09` UI page 6
- **Files:** `web/src/pages/Report.tsx`, `web/src/pages/Report.test.tsx`
- **Spec:** renders the HTML report in a sandboxed iframe, with download buttons (JSON, MD, HTML). The fallback when the UI is cut is `reval report --html` (P4-13).
- **Acceptance:** `npm --prefix web test -- Report` passes a render test.

## P6-13 — GitHub Action
- **Owner:** sonnet · **Depends on:** P3-09 · **Read first:** `docs/09` (`diff --format markdown`, exit codes)
- **Files:** `.github/actions/reval-diff/action.yml` (composite), `.github/workflows/reval-demo.yml`, `tests/integration/test_action_yaml.py`
- **Spec:** on `pull_request`: `actions/checkout` with `fetch-depth: 0`, install reval, run `reval diff origin/${{ github.base_ref }} HEAD --format markdown > reval.md`, and post or update one PR comment
  (`actions/github-script`). The exit code follows `docs/09`. It uses only the lock files (no data). Permissions: `contents: read`, `pull-requests: write`.
- **Acceptance:** `.venv/Scripts/python -m pytest tests/integration/test_action_yaml.py` parses both YAML files and checks `fetch-depth: 0`, the permissions, and the diff command. NEEDS HUMAN: a demo PR in the repo shows the comment.
- **Pitfalls:** never print secrets.

## P6-14 — Docker Compose
- **Owner:** sonnet · **Depends on:** P6-06, P6-12 · **Read first:** ADR 0003
- **Files:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- **Spec:** a multi-stage build (web build, then the Python runtime). The `api` service serves the UI and API, mounts `examples/motor_thermal` read-only and a volume for `.reval`, and has a healthcheck.
  A `db` (postgres:16) service sits behind a compose profile `postgres`, used only if P6-05's Postgres part was done.
- **Acceptance:** `docker compose config` validates. NEEDS HUMAN: `docker compose up --build`, then `http://localhost:8000` shows the claim board for the motor example.

## P6-15 — Usability check (RQ5, optional)
- **Owner:** human (sonnet prepares the materials) · **Depends on:** P6-11 · **Read first:** `docs/06` §8
- **Files:** `docs/research/usability-protocol.md`, `docs/research/usability-results.csv`, `bench/analysis/usability.py`
- **Spec:** Sonnet drafts the protocol: 3 tasks, counterbalancing, the SUS questionnaire, consent text, and an anonymous data sheet. The student runs 5–8 sessions after any required ethics approval.
- **Acceptance:** anonymized results exist, and `python -m bench.analysis.usability` computes SUS and task accuracy from the CSV.
