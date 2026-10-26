# 09 — CLI, API and UI

## CLI (`reval`, Typer)

| Command | Does |
|---|---|
| `reval init` | Create a starter `reval.yaml` + `.reval/` store in the current repo |
| `reval snapshot [--write] [--check]` | Compute the working-tree snapshot and store it. `--write` writes `reval.lock.json` (ADR 0005). `--check` exits 1 if the committed lock differs from the live state. |
| `reval status [--rev REV] [--claim ID] [--format table\|json]` | Assess all claims |
| `reval diff A [B] [--format table\|json\|markdown]` | Change set + affected claims + freshness classes between two revisions (reads `reval.lock.json` via `git show`). One revision compares it to the working tree. `markdown` is used for PR comments. |
| `reval plan [--budget N] [--planner ilp\|greedy\|all]` | Compute a revalidation plan for the current snapshot |
| `reval run [--all \| --plan ID] [--only PRODUCER]` | Execute producers (`--all`: every producer × subject; `--plan`: a stored plan's runs), store evidence append-only, re-assess |
| `reval explain CLAIM` | Justification tree with reasons (deterministic text) |
| `reval report [--html] [--out PATH]` | Render the decision-validity report |
| `reval graph [--claim ID] --out graph.json` | Export the evidence graph |
| `reval serve` | Start API + UI locally |
| `reval api-schema [--out PATH]` | Write the OpenAPI schema (input to the generated TS client) |
| `reval db upgrade` | Apply Alembic migrations to the configured store |

Exit codes for CI: `0` all claims accepted · `1` some claims stale/inconclusive · `2` some claim violated · `3` usage/config error.

## REST API (FastAPI, `/api/v1`)

Single project: the server serves the one project at `REVAL_PROJECT_ROOT`, and `{p}` is always `default`. Other values return 404.
`/projects` lists exactly that one project. There is no `POST /projects`.

```
GET  /projects
GET  /projects/{p}/snapshots                    POST /projects/{p}/snapshots      (working tree)
GET  /projects/{p}/diff?from=&to=
GET  /projects/{p}/claims?snapshot=&status=
GET  /projects/{p}/claims/{c}/assessment?snapshot=
GET  /projects/{p}/claims/{c}/justification?snapshot=
GET  /projects/{p}/evidence/{e}
GET  /projects/{p}/graph?snapshot=&focus=
POST /projects/{p}/plans                        {snapshot, budget?, planner}
GET  /projects/{p}/plans/{id}
POST /projects/{p}/plans/{id}/execute           → job
GET  /jobs/{id}                                 (poll; SSE stream at /jobs/{id}/events)
GET  /projects/{p}/reports/{id}?format=json|html|md
```

All responses are Pydantic models from `reval.domain`, so the OpenAPI schema is the single source of truth and the TS client is generated from it.

## UI pages (Vite + React + TS)

1. **Claim board:** a status grid (claims × snapshots) colored by status, filterable by requirement and criticality. The headline: "3 claims need revalidation since `a1b2c3`".
2. **Claim detail:** status + reasons. The justification tree (policy clause → evidence → dependencies). An **envelope plot**: the subject's trajectory projected onto two chosen features over the applicability-domain region, with the out-of-domain segment highlighted. Interval-vs-limit chart.
3. **Change timeline:** commits/snapshots with change sets. Click a change to highlight its influence cone.
4. **Graph explorer:** an interactive DAG with cone highlighting. Collapses to claim level by default.
5. **Planner:** obligations table, budget slider (re-solve on change), plan runs with costs, an "Execute" button (job progress via SSE), and before/after status.
6. **Report view:** the rendered report with hashes, a disclaimer, and an export button.

Status colors must not be the only signal. Each status also gets an icon and a text label (accessibility).

## Report format (canonical JSON → rendered)

```
report_id, created_at, reval_version, project, snapshot_id, git_rev
disclaimer: "ReVal reports the state of recorded evidence against declared requirements. It does not certify safety."
summary: counts by status
claims[]: id, requirement, subject, status, reasons[], evidence[] (id, producer, verdict, interval, freshness, provenance)
changes[]: (if diff-based)
plan: runs[], total_cost, unrestorable[] (no cover at any budget), deferred[] (restorable, over budget)
hashes: input_hash per assessment, report_hash
```

`report_hash` = SHA-256 of the canonical JSON of the report **excluding `created_at`, `report_id` and `report_hash`**, so the same
inputs always give the same hash. The clock is injected by the services/CLI layer. Tests pass a fixed value, which keeps golden files stable.
