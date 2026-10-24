# Phase 6 — API, web workspace, CI integration (roadmap weeks 20–26, milestone M6)

**Read first for every task:** `AGENTS.md`, `docs/09-api-and-ui.md`, `docs/10-interfaces.md`, `docs/adr/0003-local-first-storage.md`.
**Phase goal (M6 DoD):** `docker compose up` gives a working workspace on the motor example. The demo PR shows the GitHub Action comment.
**Cut line:** if behind schedule, do P6-01…P6-04 and P6-12 only (the API + static report viewer). See `docs/07-roadmap.md`.
**Frontend stack:** Vite + React 18 + TypeScript (strict), TanStack Query, `openapi-typescript` + `openapi-fetch` (generated client), `@xyflow/react`, `react-plotly.js` (or `plotly.js-dist-min`), Vitest + Testing Library. Pin exact versions in `package.json`.

---

## P6-01 — FastAPI app skeleton
- **Owner:** sonnet · **Depends on:** P4-15
- **Files:** `src/reval/api/__init__.py`, `src/reval/api/app.py`, `src/reval/api/deps.py`, `tests/integration/api/test_health.py`
- **Spec:** `create_app(settings) -> FastAPI`, mounted at `/api/v1`. `GET /api/v1/health` → `{status, version}`. A dependency injects a `Project` opened from `REVAL_PROJECT_ROOT`. Response models are **imported from `reval.domain`/`reval.report`**, never redefined. `reval serve` launches uvicorn.
- **Acceptance:** `TestClient` health test. `GET /openapi.json` validates.

## P6-02 — Read endpoints: projects, snapshots, claims, evidence, diff, graph
- **Owner:** sonnet · **Depends on:** P6-01
- **Files:** `src/reval/api/routes/{projects,snapshots,claims,evidence,diff,graph}.py`, tests
- **Spec:** exactly the routes in `docs/09`. `graph` returns `{nodes:[{id,type,label,status?}], edges:[{source,target,type}]}`, optionally focused on a claim cone. Pagination: `?limit&offset` on lists.
- **Acceptance:** integration tests on the toy project for every route, including a 404 for unknown ids.

## P6-03 — Plans, jobs, SSE
- **Owner:** sonnet · **Depends on:** P6-02
- **Files:** `src/reval/api/routes/{plans,jobs}.py`, tests
- **Spec:** `POST /plans` (body: snapshot, budget?, planner) → plan. `POST /plans/{id}/execute` → job id. The job runs in a background thread using `services.jobs`. `GET /jobs/{id}` and `GET /jobs/{id}/events` (SSE: `state`, `progress`, `done`).
- **Acceptance:** a test executes a plan on the toy project and polls to `done`. The SSE test reads at least one event.
- **Pitfalls:** SQLite + threads: use one engine with `check_same_thread=False` and a session per request/job.

## P6-04 — Report endpoints
- **Owner:** sonnet · **Depends on:** P6-02, P4-13
- **Spec:** `GET /reports/{id}?format=json|html|md`. `POST /reports` (snapshot) → build and store.
- **Acceptance:** tests for all three formats. The HTML contains the disclaimer.

## P6-05 — Alembic migrations + PostgreSQL
- **Owner:** sonnet · **Depends on:** P6-01
- **Files:** `src/reval/store/migrations/` (alembic env + initial revision), `alembic.ini`, CI job with a `postgres:16` service
- **Spec:** the initial migration matches the `docs/10` §8 tables. `reval db upgrade`. The store selects the URL from `REVAL_DATABASE_URL`.
- **Acceptance:** the CI job runs the integration tests against Postgres. `alembic check` reports no drift.

## P6-06 — Web scaffold + generated client
- **Owner:** sonnet · **Depends on:** P6-02
- **Files:** `web/` (Vite React TS template), `web/src/api/schema.d.ts` (generated), `web/src/api/client.ts`, `web/package.json` scripts: `dev`, `build`, `test`, `gen:api`
- **Spec:** `npm run gen:api` runs `openapi-typescript http://localhost:8000/api/v1/openapi.json -o src/api/schema.d.ts` (also a file-based variant from `reval api-schema > openapi.json`). App shell: left nav (Claims, Changes, Graph, Planner, Reports), a project/snapshot selector in the header. Light/dark themes via CSS variables. FastAPI serves `web/dist` at `/` in `reval serve`.
- **Acceptance:** `npm --prefix web run build` and `npm --prefix web test` pass. The CI job builds the web app.
- **Pitfalls:** never hand-write API types. Regenerate them.

## P6-07 — Claim board page
- **Owner:** sonnet · **Depends on:** P6-06
- **Spec:** a grid of claims × recent snapshots. A cell shows status icon + label (never color alone). Filters: requirement, criticality, status. A headline count "N claims need revalidation since <rev>". Clicking a cell → claim detail.
- **Acceptance:** Vitest + Testing Library render test with mocked client. An a11y check (`@axe-core/react` in dev or `vitest-axe`) has no violations.

## P6-08 — Claim detail: justification tree + envelope plot
- **Owner:** sonnet · **Depends on:** P6-07
- **Spec:** status + reasons. A collapsible justification tree (clause → evidence → deps). The **envelope plot**: two selectable features. The AD region is drawn from the `domain_report` (box) + training-point density (downsampled points served by a new endpoint `GET /claims/{c}/envelope`). The subject trajectory is overlaid, with the out-of-domain segment highlighted. An interval-vs-limit chart per evidence.
- **Acceptance:** render tests. A screenshot check with the built-in browser against the motor example (human verifies plausibility).

## P6-09 — Change timeline
- **Owner:** sonnet · **Depends on:** P6-06
- **Spec:** a list of snapshots (git rev, date, change counts). Clicking one shows the change set grouped by artifact. Selecting a change highlights affected claims (via `/graph?focus=`).
- **Acceptance:** render tests with fixtures.

## P6-10 — Graph explorer
- **Owner:** sonnet · **Depends on:** P6-06
- **Spec:** `@xyflow/react` with a dagre/elk layout, collapsed to claim level by default, expanding on click. Cone highlighting for a selected node. Node shapes per type and a status badge.
- **Acceptance:** renders 500 nodes without freezing (a perf smoke test measures the initial render < 2 s in jsdom-free Playwright, or a manual check by the human).

## P6-11 — Planner page
- **Owner:** sonnet · **Depends on:** P6-03, P6-06
- **Spec:** an obligations table, a planner selector, and a budget slider (debounced re-solve via `POST /plans`). The plan table (run, producer, subject, cost, discharges). An "Execute" button → job progress via SSE → before/after status table.
- **Acceptance:** render + interaction tests with a mocked client.

## P6-12 — Report view + static viewer fallback
- **Owner:** sonnet · **Depends on:** P6-04
- **Spec:** renders the HTML report in an iframe with download buttons (JSON/MD/HTML). The fallback (cut line 4) is `reval report --html`, which already exists.
- **Acceptance:** render test.

## P6-13 — GitHub Action
- **Owner:** sonnet · **Depends on:** P4-15
- **Files:** `.github/actions/reval-diff/action.yml` (composite), `.github/workflows/reval-demo.yml`
- **Spec:** on `pull_request`: install reval, run `reval diff origin/${{ github.base_ref }} HEAD --format markdown > reval.md`, post or update a single PR comment (via `gh pr comment --edit-last` or `actions/github-script`), exit code per `docs/09`.
- **Acceptance:** the demo PR in the repo shows the comment (human verifies). The action uses only the lock files (no data needed).
- **Pitfalls:** use the `GITHUB_TOKEN` with minimal permissions (`pull-requests: write`). Never print secrets.

## P6-14 — Docker Compose
- **Owner:** sonnet · **Depends on:** P6-05, P6-06
- **Files:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- **Spec:** a multi-stage build (web build → python runtime). Services: `db` (postgres:16), `api` (serves UI + API, mounts `examples/motor_thermal` read-only plus a volume for `.reval`). A healthcheck.
- **Acceptance:** `docker compose up --build` → `http://localhost:8000` shows the claim board for the motor example.

## P6-15 — Usability check (RQ5, optional)
- **Owner:** human (sonnet prepares materials) · **Depends on:** P6-11
- **Spec:** Sonnet drafts `docs/research/usability-protocol.md` (3 tasks, counterbalancing, SUS questionnaire, consent text, anonymous data sheet). The human runs the sessions with 5–8 participants after any required ethics approval.
- **Acceptance:** anonymized results in `docs/research/usability-results.csv`. The analysis is scripted.
