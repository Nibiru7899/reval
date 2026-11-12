# Tutorial: add ReVal to your project

You will start from an empty folder and end with a project where ReVal tells you which claims survive a change. The domain is deliberately tiny:
a **cantilever beam** with an analytic truth model, so you can check every number with a calculator.

!!! abstract "What you will build"
    - 2 requirements: tip deflection at most 15 mm; bending stress at most 150 MPa.
    - 1 analytic producer (closed-form Euler-Bernoulli formulas) and 1 surrogate-model producer (a fitted slope with an empirical interval).
    - A change (load 600 N to 700 N), and the cycle `diff`, `plan`, `run`, `report`.

    The finished project is `examples/beam_toy/`, and `tests/integration/test_tutorial_beam.py` executes every command on this page, so it cannot drift.

**Time:** the target is under an hour from install to a first useful `diff`. Prerequisites: Python 3.12+, git, ReVal installed ([quickstart](quickstart.md)),
and pandas (`pip install "reval[motor]"` or `-e ".[motor]"`), because the surrogate reads a CSV.

## The physics, so you can check the answers

For a cantilever with tip load *P*, length *L*, width *b*, height *h* and Young's modulus *E* (units N, mm, MPa):

```text
tip deflection   delta = 4 P L^3 / (E b h^3)
bending stress   sigma = 6 P L / (b h^2)
```

With P = 600 N, L = 500 mm, b = 40 mm, h = 20 mm, E = 70 000 MPa (aluminium): delta = 13.39 mm and sigma = 112.5 MPa. Both pass. At P = 700 N,
delta = 15.63 mm, which breaks the 15 mm limit, while sigma = 131.3 MPa still passes.

## 1. Start a project

```bash
mkdir beam && cd beam
git init
printf '.reval/\n__pycache__/\n' > .gitignore
reval init
```

```console
$ reval init
wrote .../beam/reval.yaml
created .reval/ (add it to .gitignore)
```

`reval init` writes a commented starter manifest and creates the `.reval/` store; it never overwrites an existing manifest. We will replace the
starter with the real one below.

## 2. Give ReVal things to track: params and data

Parameters live in a small YAML file. **Each field you list in a producer's `depends_on` is tracked separately**, which is what lets ReVal keep evidence fresh
when an unrelated field changes.

```yaml title="params/beam.yaml"
--8<-- "examples/beam_toy/params/beam.yaml"
```

The surrogate is trained on test samples. To keep the tutorial deterministic, a script generates the samples and fits the model (a slope through the origin);
in a real project these would be your measurements and your trained model file:

```python title="scripts/make_data.py"
--8<-- "examples/beam_toy/scripts/make_data.py"
```

```bash
python scripts/make_data.py       # writes inputs/samples.csv and fitted/surrogate.json
```

!!! warning "Name your folders carefully"
    The repository's `.gitignore` excludes `data/` and `models/` under `examples/` (large files are never committed). The beam example uses `inputs/` and
    `fitted/` so its tiny files are tracked. In your own project use whatever folders you like.

## 3. Write the producers

A producer is a function `(subject, ctx) -> ProducerOutput` registered with `@producer`. It must declare **everything it reads**. Reading an
undeclared artifact or parameter raises an error, and it is the declaration that drives impact analysis.

```python title="beam/producers.py"
--8<-- "examples/beam_toy/beam/producers.py"
```

Points to notice:

- `kind` decides how the result is judged and which policy clauses it can satisfy. `ANALYTIC` returns exact values (`exact_result`);
  `ML_PREDICTION` returns an interval and an `in_domain` flag (`interval_result`). Out-of-domain predictions can never pass.
- `cost` is what the planner minimises. Here the analytic check costs 2 and the surrogate 0.5.
- `depends_on` uses selectors: `params#/beam/load_N` is one field of a params file; `samples[x_mm,defl_mm]` is two columns of a dataset.
- `predictors=["surrogate"]` names the model that computed the value. Two items are *independent* only if their predictors are disjoint.
- Everything is in a package `beam/` next to the manifest (add an empty `beam/__init__.py`).

## 4. Write the manifest

```yaml title="reval.yaml"
--8<-- "examples/beam_toy/reval.yaml"
```

- `quantities` fixes the unit of each quantity once, and requirements, producers and evidence must use it (units are explicit at every boundary).
- `artifacts` lists tracked files; `surrogate` is `derived_from` the samples, so a change to the samples also invalidates what depends on the model.
- Each `requirement` has a `criticality` that selects the default evidence policy (see [Concepts](concepts.md#policies-what-evidence-is-enough)).
  Both are `low`, so *any one* of ML-in-domain, physics, measurement or analytic evidence is enough.
- `claims` bind a requirement to a subject; `producers` lists the Python modules to import.

## 5. Lock, check, run

```console
$ reval snapshot --write
snapshot 45d88dc0996cc39a26a5870368d749ed9c32fd3a49a7a42cd80d54eb9f6727e0
wrote .../beam/reval.lock.json

$ reval status
CLAIM     STATUS        CLAUSE  REASONS
C-DEFL    INCONCLUSIVE  -       no_evidence
C-STRESS  INCONCLUSIVE  -       no_evidence

$ reval run --all
ran 3 producer results
CLAIM     BEFORE        AFTER      CLAUSE
C-DEFL    INCONCLUSIVE  SUPPORTED  0
C-STRESS  INCONCLUSIVE  SUPPORTED  3
```

Three results: one analytic run produced two (deflection and stress), the surrogate one. `C-DEFL` is supported by clause 0 (the in-domain ML prediction),
`C-STRESS` by clause 3 (analytic). Commit the baseline, including `reval.lock.json`:

```bash
git add -A && git commit -m "baseline"
```

## 6. Change a parameter

The design team proposes a heavier load: edit `params/beam.yaml`, `load_N: 600` to `load_N: 700`, re-lock and commit.

```bash
sed -i 's/load_N: 600/load_N: 700/' params/beam.yaml
reval snapshot --write && git commit -am "load 600 -> 700 N"
```

```console
$ reval diff HEAD~1 HEAD
KIND           TARGET               DETAIL
FIELD_CHANGED  params#/beam/load_N  600 -> 700; delta 100

CLAIM     BEFORE     AFTER  AFFECTED  REASONS
C-DEFL    SUPPORTED  STALE  yes       evidence_invalidated
C-STRESS  SUPPORTED  STALE  yes       evidence_invalidated
```

Both claims depend on `load_N`, and neither producer declared a tolerance for it, so the old evidence is invalidated (fail closed). Nothing has
been re-proved, so both are `STALE`, not `SUPPORTED`.

## 7. Plan the cheapest restoration

```console
$ reval plan
PRODUCER                      SUBJECT  COST  DISCHARGES
beam.producers:beam_analytic  B1       2     C-DEFL/3/0, C-STRESS/3/0
planner ilp  objective min_cost  budget -  solver OPTIMAL
total cost 2  runs 1
restores: C-DEFL, C-STRESS
unrestorable: -
deferred: -
```

The planner chose **one** run of cost 2 rather than the surrogate (0.5) plus the analytic check (2): the analytic run covers both claims, and the
surrogate could only help one of them. This is the minimum-cost set, not the cheapest single producer.

## 8. Run the plan and read the result

```console
$ reval run --plan latest
ran 1 planned runs (0 failed), 2 evidence items
PRODUCER                      SUBJECT  STATE      ERROR
beam.producers:beam_analytic  B1       SUCCEEDED  -
CLAIM     BEFORE  AFTER      CLAUSE
C-DEFL    STALE   VIOLATED   -
C-STRESS  STALE   SUPPORTED  3
```

The stress claim is restored. The deflection claim is now **`VIOLATED`**: the fresh analytic value is 15.625 mm against a 15 mm limit. That is the
useful answer a change should produce. `reval explain` shows the evidence tree:

```console
$ reval explain C-DEFL
C-DEFL: VIOLATED  [R-DEFL: tip_deflection <= 15 mm; criticality low; subject B1]
|-- reasons
|   `-- requirement_violated: fresh evidence shows the requirement is not met
|       `-- evidence: d957ccee845f
|-- clauses (policy low)
|   |-- clause 0 [not satisfied]: ml_prediction (in domain)
|   |-- clause 1 [not satisfied]: physics_sim
|   |-- clause 2 [not satisfied]: measurement
|   `-- clause 3 [not satisfied]: analytic
`-- evidence
    |-- 1b5564958085 beam.producers:beam_surrogate (ml_prediction): verdict pass, recorded pass, freshness invalidated, interval [13.2965, 13.4706] mm
    |-- d957ccee845f beam.producers:beam_analytic (analytic): verdict fail, recorded fail, freshness fresh_exact, interval [15.625, 15.625] mm
    `-- da4f0015ec9b beam.producers:beam_analytic (analytic): verdict pass, recorded pass, freshness invalidated, interval [13.3929, 13.3929] mm
```

(Dependency lines trimmed.) The old surrogate result still says `pass` at 13.4 mm but is `invalidated`: ReVal will not let stale evidence argue against a fresh failure.
The old analytic value is kept too, as history (evidence is append-only). Finally render the report:

```bash
reval report --out report.md        # or --html, or --json
```

## 9. Where to go from here

- **Keep evidence fresh across small changes:** give a producer a `Tolerance` (a sensitivity and a valid range, backed by an `Assumption`) on the parameter, as `sim_temp`
  does in the mini project. Small changes then widen the interval instead of invalidating it. See [Concepts](concepts.md#freshness-is-this-evidence-still-good-after-the-change).
- **Add a second kind of evidence:** a measurement or a physics simulation as an independent source, then raise a requirement to `medium` or `high`.
- **Run it in CI:** `reval status` and `reval diff` exit non-zero when something needs attention.
- **Look at a bigger project:** the [motor tutorial](motor-tutorial.md).

!!! danger "What this does not mean"
    `SUPPORTED` means the recorded evidence satisfies the declared requirement under the declared policy. It is not a statement that the beam is safe,
    and 15 mm and 150 MPa are numbers made up for this tutorial.
