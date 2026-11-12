# Quickstart

This walks the bundled **mini project** (`tests/fixtures/mini_project`), a four-claim toy whose expected results are
derived by hand in its `EXPECTED.md`. Every command and output below was produced by running it.

## Install

ReVal needs Python 3.12 or newer and git.

=== "uv"

    ```bash
    git clone <your clone URL> reval && cd reval
    uv sync --all-extras
    uv run reval version
    ```

=== "pip"

    ```bash
    git clone <your clone URL> reval && cd reval
    python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
    pip install -e ".[motor]"
    reval version
    ```

```console
$ reval version
reval 0.0.1
```

!!! tip "Extras"
    `motor` brings pandas and scikit-learn (producers that read CSV or parquet need pandas), `server` the API, `dev` the test tools,
    and `docs` this site's toolchain.

## 1. Copy the project and put it under git

ReVal compares git revisions, so work on a throwaway copy that is a repository:

```bash
cp -r tests/fixtures/mini_project /tmp/mini && cd /tmp/mini
git init && printf '.reval/\n__pycache__/\n' > .gitignore
```

The manifest `reval.yaml` declares the artifacts (params, a dataset, a surrogate model), requirements, subjects and four claims;
`mini/producers.py` holds four producers. [Concepts](concepts.md) explains each piece.

## 2. Lock the snapshot and look at the claims

```console
$ reval snapshot --write
snapshot 886d7c2f321ea7c02e08a8ffbafed406dcef755d8e5500f74f6c0da0b4449762
wrote .../mini/reval.lock.json

$ reval status
CLAIM      STATUS        CLAUSE  REASONS
C-S1-HI    INCONCLUSIVE  -       no_evidence
C-S1-TEMP  INCONCLUSIVE  -       no_evidence
C-S2-TEMP  INCONCLUSIVE  -       no_evidence
C-SHAFT    INCONCLUSIVE  -       no_evidence
```

`reval.lock.json` records the content hash of every artifact; commit it. With no evidence yet, every claim is `INCONCLUSIVE`
(`no_evidence`), and `status` exits `1`.

## 3. Run the producers

```console
$ reval run --all
ran 6 producer results
CLAIM      BEFORE        AFTER      CLAUSE
C-S1-HI    INCONCLUSIVE  SUPPORTED  0
C-S1-TEMP  INCONCLUSIVE  SUPPORTED  0
C-S2-TEMP  INCONCLUSIVE  VIOLATED   -
C-SHAFT    INCONCLUSIVE  SUPPORTED  3
```

Evidence is stored append-only under `.reval/`. `C-S2-TEMP` is `VIOLATED` because the physics simulation's interval
`[96, 100]` degC lies entirely above the 80 degC limit (`EXPECTED.md` derives this by hand). The exit code is `2`.

## 4. Change something

Commit the baseline, then raise `load.scale` from 1.0 to 1.2 and ask what the change touches:

```bash
git add -A && git commit -m baseline
sed -i 's/scale: 1.0/scale: 1.2/' params/params.yaml
reval snapshot --write && git commit -am "load scale 1.2"
```

```console
$ reval diff HEAD~1 HEAD
KIND           TARGET              DETAIL
FIELD_CHANGED  params#/load/scale  1.0 -> 1.2; delta 0.2

CLAIM      BEFORE     AFTER      AFFECTED  REASONS
C-S1-HI    SUPPORTED  SUPPORTED  yes       policy_satisfied
C-S1-TEMP  SUPPORTED  SUPPORTED  yes       policy_satisfied
C-S2-TEMP  VIOLATED   STALE      yes       evidence_invalidated
C-SHAFT    SUPPORTED  SUPPORTED  no        policy_satisfied
```

Three things to read here:

- `C-SHAFT` is **not affected**: nothing it depends on changed, so its evidence stays fresh and costs nothing to keep.
- `C-S1-*` stay supported because the *measurement* evidence does not depend on the load scale.
- `C-S2-TEMP` went from `VIOLATED` to `STALE`, not to "fine". A change must never turn a refuted claim into an accepted one
  without new evidence (see [Concepts](concepts.md#status-rules)).

## 5. Plan, run, explain, report

```console
$ reval plan
PRODUCER                     SUBJECT  COST  DISCHARGES
mini.producers:predict_temp  S2       1     C-S2-TEMP/0/0
mini.producers:sim_temp      S2       3     C-S2-TEMP/0/1, rerun:mini.producers:sim_temp@S2
planner ilp  objective min_cost  budget -  solver OPTIMAL
total cost 4  runs 2
restores: C-S2-TEMP
unrestorable: -
deferred: -

$ reval run --plan latest
ran 2 planned runs (0 failed), 2 evidence items
PRODUCER                     SUBJECT  STATE      ERROR
mini.producers:predict_temp  S2       SUCCEEDED  -
mini.producers:sim_temp      S2       SUCCEEDED  -
CLAIM      BEFORE     AFTER      CLAUSE
C-S1-HI    SUPPORTED  SUPPORTED  0
C-S1-TEMP  SUPPORTED  SUPPORTED  1
C-S2-TEMP  STALE      VIOLATED   -
C-SHAFT    SUPPORTED  SUPPORTED  3
```

The plan re-ran only the two producers that matter for `C-S2-TEMP` (total cost 4); it did not re-run the 10-unit measurement or touch `C-SHAFT`.
Re-proving the claim at the new load ends in `VIOLATED` again, which is the honest answer. `reval explain` shows why a claim has its status:

```console
$ reval explain C-S1-TEMP
C-S1-TEMP: SUPPORTED  [R-TEMP: temp_peak <= 80 degC; criticality medium; subject S1]
|-- reasons
|   `-- policy_satisfied: policy medium clause 1 is satisfied by recorded evidence
|       `-- evidence: fbb4fcdea172
|-- clauses (policy medium)
|   |-- clause 0 [not satisfied]: ml_prediction (in domain) AND physics_sim (independent of ml_prediction)
|   |-- clause 1 [satisfied]: measurement
|   `-- clause 2 [not satisfied]: analytic (fidelity>=3)
`-- evidence
    |-- 1de15eb7ceda mini.producers:predict_temp (ml_prediction): verdict pass, recorded pass, freshness invalidated, interval [39.5, 40.5] degC
    |-- f74483c06dc8 mini.producers:sim_temp (physics_sim): verdict pass, recorded pass, freshness carry_forward, interval [46, 74] degC
    `-- fbb4fcdea172 mini.producers:measure_temp (measurement): verdict pass, recorded pass, freshness fresh_exact, interval [39, 40] degC, used in satisfied clause
```

(Dependency lines are trimmed here.) Note `sim_temp` is `carry_forward` with a widened interval `[46, 74]`: it declares a sensitivity tolerance on
`params#/load/scale`, so a small change widens the interval instead of discarding the evidence. Finally, `reval report` renders everything as Markdown
(`--html` and `--json` also work):

```console
$ reval report
# Decision-validity report: mini

_ReVal reports the state of recorded evidence against declared requirements. It does not certify safety._

**3 of 4 claims are supported by recorded evidence; 1 claim needs attention.**

Supported: 3 · Waived: 0 · Stale: 0 · Inconclusive: 0 · Violated: 1
...
```

## Next

- Read [Concepts](concepts.md) for what the columns and statuses mean.
- Put ReVal on your own project: [Add ReVal to your project](tutorial-new-project.md).
- Every flag: [CLI reference](cli.md).
