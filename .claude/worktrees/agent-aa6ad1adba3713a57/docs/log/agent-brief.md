# Brief for implementation subagents (orchestrated runs)

You implement exactly the task(s) you are given, in `D:\ProjectsOS\ReVal` (Windows; use the Bash tool with POSIX syntax).

1. Read `AGENTS.md`, your task spec in `docs/tasks/phase-*.md`, and the `docs/10-interfaces.md` sections it names. Signatures in docs/10 are binding.
2. Other agents are working **in the same checkout at the same time** on other files:
   - Touch only the files your task lists, plus at most a tiny helper. If you need a change in another file, say so in your report; don't make it.
   - **Don't run git commands that change state** (no add, commit, switch, stash, checkout). `git status` and `git diff` are fine.
   - **Don't edit** `docs/tasks/BACKLOG.md`, `pyproject.toml`, or `.claude/`.
3. Run checks on your files only (other files may be half-written). **Never run `ruff format .` or `ruff check --fix .` repo-wide, and never restore other files from git.** Those commands destroy other agents' work.
   - `.venv/Scripts/python -m ruff check <your files>`
   - `.venv/Scripts/python -m ruff format <your files>` (it may reformat them)
   - `.venv/Scripts/python -m mypy src` (only if you touched `src/`)
   - `.venv/Scripts/python -m pytest <your test files> -q`
   - The data-marked tests too, if the task has them: the real data is at `examples/motor_thermal/data/raw/measures_v2.csv`, and the parquet at `examples/motor_thermal/data/processed/measures.parquet` once P1-01 is done.
4. Environment notes:
   - pandas is 3.x (copy-on-write; the default string dtype is `str`).
   - scikit-learn 1.9 and scipy 1.18. There are 20 CPU cores.
   - Keep any single test under ~20 s, and mark longer ones `@pytest.mark.slow`.
5. If the spec is ambiguous on engineering semantics, pick the conservative option and list it under "Decisions" in your report. Don't stop.
6. Report in at most 12 lines:
   - the files written;
   - the acceptance results (paste the pytest summary line);
   - your decisions;
   - anything another task must know, such as a function name you added.
