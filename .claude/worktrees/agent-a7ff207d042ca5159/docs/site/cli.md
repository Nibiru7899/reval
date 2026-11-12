# CLI reference

!!! note "Generated"
    This page is generated from the live Typer app by `scripts/gen_cli_docs.py`. Do not edit it by hand.

**Exit codes** (shared by `status`, `run` and `diff`): `0` every claim accepted, `1` some claim stale or
inconclusive, `2` some claim violated, `3` error. A non-zero exit is a signal, not a crash.

Every command takes `--project <path>` (default: the current directory).

## `reval`

```text

 Usage: reval [OPTIONS] COMMAND [ARGS]...

 ReVal: which engineering conclusions survive a change, and the cheapest way
 to re-prove the rest.

+- Options -------------------------------------------------------------------+
| --install-completion          Install completion for the current shell.     |
| --show-completion             Show completion for the current shell, to     |
|                               copy it or customize the installation.        |
| --help                        Show this message and exit.                   |
+-----------------------------------------------------------------------------+
+- Commands ------------------------------------------------------------------+
| version     Print the installed ReVal version.                              |
| snapshot    Compute the working-tree snapshot; optionally write or check    |
|             the lock file.                                                  |
| status      Assess every claim. Exit 0 all accepted, 1 stale or             |
|             inconclusive, 2 violated, 3 error.                              |
| plan        Plan the cheapest runs that restore stale or inconclusive       |
|             claims (stored, nothing is run).                                |
| run         Execute producers, store the evidence (append-only) and         |
|             re-assess.                                                      |
| diff        Change set, evidence freshness and affected claims between      |
|             revisions (reads reval.lock.json).                              |
| init        Write a commented starter reval.yaml and create the .reval/     |
|             store (never overwrites a manifest).                            |
| graph       Export the evidence graph of the working-tree snapshot as JSON  |
|             (nodes and edges).                                              |
| report      Render the decision-validity report: recorded evidence against  |
|             declared requirements.                                          |
| explain     Justification tree for one claim: status, reasons, clauses,     |
|             evidence and its dependencies.                                  |
| serve       Start the API (and the web UI once built) for the project, on   |
|             localhost by default.                                           |
| api-schema  Write the OpenAPI schema (input to the generated TypeScript     |
|             client).                                                        |
| db          Database maintenance.                                           |
+-----------------------------------------------------------------------------+
```

## `reval version`

```text

 Usage: reval version [OPTIONS]

 Print the installed ReVal version.

+- Options -------------------------------------------------------------------+
| --help          Show this message and exit.                                 |
+-----------------------------------------------------------------------------+
```

## `reval snapshot`

```text

 Usage: reval snapshot [OPTIONS]

 Compute the working-tree snapshot; optionally write or check the lock file.

+- Options -------------------------------------------------------------------+
| --project        <path>  Project root (default: current directory).         |
|                          [default: .]                                       |
| --write                  Write reval.lock.json.                             |
| --check                  Exit 1 if the lock differs from the live state.    |
| --help                   Show this message and exit.                        |
+-----------------------------------------------------------------------------+
```

## `reval status`

```text

 Usage: reval status [OPTIONS]

 Assess every claim. Exit 0 all accepted, 1 stale or inconclusive, 2 violated,
 3 error.

+- Options -------------------------------------------------------------------+
| --project        <path>        Project root (default: current directory).   |
|                                [default: .]                                 |
| --format         <table|json>  table or json [default: table]               |
| --claim          <str>         Show only this claim.                        |
| --help                         Show this message and exit.                  |
+-----------------------------------------------------------------------------+
```

## `reval plan`

```text

 Usage: reval plan [OPTIONS]

 Plan the cheapest runs that restore stale or inconclusive claims (stored,
 nothing is run).

+- Options -------------------------------------------------------------------+
| --project        <path>            Project root (default: current           |
|                                    directory).                              |
|                                    [default: .]                             |
| --budget         <float>           Cost budget; maximizes restored          |
|                                    criticality within it.                   |
| --planner        <ilp|greedy|all>  ilp, greedy or all [default: ilp]        |
| --format         <table|json>      table or json [default: table]           |
| --help                             Show this message and exit.              |
+-----------------------------------------------------------------------------+
```

## `reval run`

```text

 Usage: reval run [OPTIONS]

 Execute producers, store the evidence (append-only) and re-assess.

+- Options -------------------------------------------------------------------+
| --project        <path>  Project root (default: current directory).         |
|                          [default: .]                                       |
| --all                    Run every producer on every subject it is          |
|                          available for.                                     |
| --plan           <str>   Run a stored plan's runs: a plan id or 'latest'.   |
| --only           <str>   With --plan: run only this producer's planned      |
|                          runs.                                              |
| --help                   Show this message and exit.                        |
+-----------------------------------------------------------------------------+
```

## `reval diff`

```text

 Usage: reval diff [OPTIONS] {a} [b]

 Change set, evidence freshness and affected claims between revisions (reads
 reval.lock.json).

+- Arguments -----------------------------------------------------------------+
| *    a      <str>  Base revision. [required]                                |
|      b      <str>  Second revision (default: the working tree).             |
+-----------------------------------------------------------------------------+
+- Options -------------------------------------------------------------------+
| --project        <path>                 Project root (default: current      |
|                                         directory).                         |
|                                         [default: .]                        |
| --format         <table|json|markdown>  table, json or markdown             |
|                                         [default: table]                    |
| --help                                  Show this message and exit.         |
+-----------------------------------------------------------------------------+
```

## `reval init`

```text

 Usage: reval init [OPTIONS]

 Write a commented starter reval.yaml and create the .reval/ store (never
 overwrites a manifest).

+- Options -------------------------------------------------------------------+
| --project        <path>  Project root (default: current directory).         |
|                          [default: .]                                       |
| --help                   Show this message and exit.                        |
+-----------------------------------------------------------------------------+
```

## `reval graph`

```text

 Usage: reval graph [OPTIONS]

 Export the evidence graph of the working-tree snapshot as JSON (nodes and
 edges).

+- Options -------------------------------------------------------------------+
| *  --out            <path>  Where to write the graph JSON. [required]       |
|    --project        <path>  Project root (default: current directory).      |
|                             [default: .]                                    |
|    --claim          <str>   Keep only this claim's cone and what it         |
|                             influences.                                     |
|    --help                   Show this message and exit.                     |
+-----------------------------------------------------------------------------+
```

## `reval report`

```text

 Usage: reval report [OPTIONS]

 Render the decision-validity report: recorded evidence against declared
 requirements.

+- Options -------------------------------------------------------------------+
| --project        <path>  Project root (default: current directory).         |
|                          [default: .]                                       |
| --html                   Self-contained HTML instead of Markdown.           |
| --json                   Canonical report JSON.                             |
| --out            <path>  Write here instead of stdout.                      |
| --since          <str>   Git revision; adds the changes since it to the     |
|                          report.                                            |
| --help                   Show this message and exit.                        |
+-----------------------------------------------------------------------------+
```

## `reval explain`

```text

 Usage: reval explain [OPTIONS] {claim}

 Justification tree for one claim: status, reasons, clauses, evidence and its
 dependencies.

+- Arguments -----------------------------------------------------------------+
| *    claim      <str>  Claim id. [required]                                 |
+-----------------------------------------------------------------------------+
+- Options -------------------------------------------------------------------+
| --project        <path>  Project root (default: current directory).         |
|                          [default: .]                                       |
| --help                   Show this message and exit.                        |
+-----------------------------------------------------------------------------+
```

## `reval serve`

```text

 Usage: reval serve [OPTIONS]

 Start the API (and the web UI once built) for the project, on localhost by
 default.

+- Options -------------------------------------------------------------------+
| --project        <path>  Project root (default: current directory).         |
|                          [default: .]                                       |
| --host           <str>   Bind address. [default: 127.0.0.1]                 |
| --port           <int>   Bind port. [default: 8000]                         |
| --help                   Show this message and exit.                        |
+-----------------------------------------------------------------------------+
```

## `reval api-schema`

```text

 Usage: reval api-schema [OPTIONS]

 Write the OpenAPI schema (input to the generated TypeScript client).

+- Options -------------------------------------------------------------------+
| --out         <path>  Where to write the OpenAPI JSON.                      |
|                       [default: openapi.json]                               |
| --help                Show this message and exit.                           |
+-----------------------------------------------------------------------------+
```

## `reval db`

```text

 Usage: reval db [OPTIONS] COMMAND [ARGS]...

 Database maintenance.

+- Options -------------------------------------------------------------------+
| --help          Show this message and exit.                                 |
+-----------------------------------------------------------------------------+
+- Commands ------------------------------------------------------------------+
| upgrade  Apply Alembic migrations to REVAL_DATABASE_URL (default: the       |
|          project's SQLite store).                                           |
+-----------------------------------------------------------------------------+
```

### `reval db upgrade`

```text

 Usage: reval db upgrade [OPTIONS]

 Apply Alembic migrations to REVAL_DATABASE_URL (default: the project's SQLite
 store).

+- Options -------------------------------------------------------------------+
| --project         <path>  Project root (default: current directory).        |
|                           [default: .]                                      |
| --revision        <str>   Target revision. [default: head]                  |
| --help                    Show this message and exit.                       |
+-----------------------------------------------------------------------------+
```

