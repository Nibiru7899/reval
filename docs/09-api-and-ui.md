# 09 — CLI, API and UI

## CLI (`reval`, Typer)

| Command | Does |
|---|---|
| `reval init` | Create `reval.yaml` + `.reval/` store in the current repo |
| `reval snapshot [--rev REV]` | Compute and store a snapshot (working tree or git revision) |
| `reval status [--rev REV] [--claim ID] [--format table\|json]` | Assess all claims |
| `reval diff A B` | Change set + affected claims + freshness classes between two revisions |
| `reval plan [--budget N] [--planner ilp\|greedy\|all]` | Compute a revalidation plan for the current snapshot |
| `reval run [--plan ID] [--only PRODUCER]` | Execute planned runs, store evidence, re-assess |
| `reval explain CLAIM` | Justification tree with reasons (deterministic text) |
| `reval report [--html] [--out PATH]` | Render the decision-validity report |
| `reval graph [--claim ID] --out graph.json` | Export the evidence graph |
| `reval serve` | Start API + UI locally |

Exit codes for CI: `0` all claims accepted · `1` some claims stale/inconclusive · `2` some claim violated · `3` usage/config error.

## REST API (FastAPI, `/api/v1`)

```
GET  /projects                                  POST /projects
GET  /projects/{p}/snapshots                    POST /projects/{p}/snapshots      {rev?}
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
plan: runs[], total_cost, unrestorable[]
hashes: input_hash per assessment, report_hash (over canonical JSON)
```
