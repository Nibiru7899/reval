---
name: next-task
description: Pick the next ready ReVal task from docs/tasks/BACKLOG.md and implement it end to end (spec → tests → code → checks → review → commit). Use when asked to "do the next task", "continue the backlog", or to implement a specific task ID like P2-03.
---

# next-task: implement one backlog task

Do exactly **one** task per invocation. Follow the steps in order.

## 1. Load context
1. Read `AGENTS.md` fully. Its non-negotiable rules override anything else.
2. Read `docs/tasks/BACKLOG.md`.
3. Select a task:
   - If the user named a task ID, use it.
   - Otherwise take the **lowest-ID** task with status `todo`, owner `sonnet` or `sonnet+human-review`, and every dependency `done` or `review`. Never pick `human` tasks.
   - If none qualifies, stop and report which tasks are blocked and by what.
4. In BACKLOG.md, set that task's status to `in-progress`.
5. Open the task's spec in its phase file (`docs/tasks/phase-*.md`). Read every doc listed under **Read first**, plus the `docs/10-interfaces.md` sections it references. Signatures in `docs/10-interfaces.md` are binding.

## 2. Branch
```bash
git switch main
git checkout -b feat/<task-id-lowercase>-<short-slug>   # e.g. feat/p2-04-hashers
```
Use `fix/`, `docs/`, or `bench/` instead of `feat/` if the task type says so.

## 3. Implement test-first
1. Write the tests named in the task's **Acceptance criteria** first. Watch them fail.
2. Implement until they pass. Touch only the files listed under **Files**, unless a listed file truly needs a small helper elsewhere. Mention any extra file in the commit body.
3. Keep `src/reval/core/` pure (no I/O, clock, randomness, network, LLM).
4. If semantics change, update `docs/03-domain-model.md` / `docs/10-interfaces.md` in the same change.

## 4. When the spec is ambiguous: stop, don't guess
If the spec, the interfaces, or the domain model conflict or leave a semantic decision open (statuses, freshness, verdicts, units, splits, metrics):
1. Append an entry to `docs/log/questions.md` using its template (task ID, question, options, your recommendation).
2. Set the task to `blocked` in BACKLOG.md with a pointer to the question.
3. Commit the docs change only, and report. Purely mechanical choices (naming a private helper) don't need a question.

## 5. Checks (all must pass)
Windows venv shown. Elsewhere, replace `.venv/Scripts/python` with `.venv/bin/python` or `uv run python`.
```bash
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m mypy src
.venv/Scripts/python -m pytest
```
Also run any extra command the task lists (for example `reval status` on the example project).

## 6. Review
Invoke the `reval-reviewer` subagent on the diff (`git diff main...HEAD`). Pass it the task ID. Fix every **blocker** and **major** finding, then re-run step 5. Minor findings: fix them or note them in the commit body. Optionally invoke `spec-checker` with the task ID to confirm the acceptance criteria.

## 7. Finish
1. In BACKLOG.md, set the status to `done`. Use `review` instead when the owner is `sonnet+human-review` (always), or when the task has a `NEEDS HUMAN` item.
2. Commit with Conventional Commits, referencing the task ID:
   ```
   feat(core): freshness classification (P3-03)

   <what and why, any deviations from spec>
   ```
3. **Never `git push`. Never merge into `main`.** The user fast-forward-merges each finished branch before the next task starts (BACKLOG.md, decision D26).
4. Report in ≤ 5 lines: the task, files changed, check results, reviewer outcome, the next ready task.
