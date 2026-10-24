---
name: phase-refine
description: At the start of a ReVal roadmap phase (or when tasks keep getting blocked), re-check that phase's task specs against the actual code and tighten them so a less capable model can implement them without guessing. Intended for the strongest available model (Opus).
---

# phase-refine: tighten a phase before implementation

## Inputs
A phase number (for example `3`). If none is given, use the lowest phase in `docs/tasks/BACKLOG.md` that still has `todo` tasks.

## Steps
1. Read `AGENTS.md`, `docs/07-roadmap.md` (the phase and its DoD), `docs/tasks/phase-<n>-*.md`, `docs/10-interfaces.md`, and `docs/03-domain-model.md`.
2. Read the code that exists now (`src/reval/`, `examples/`, `bench/`, `tests/`). List every place where the code differs from the interfaces doc: renamed functions, changed fields, extra parameters.
3. Read `docs/log/questions.md`. Resolve each open question that belongs to this phase. Record the decision under the question, and update the spec or domain model accordingly.
4. For each task in the phase, check:
   - **Files** are exact paths.
   - **Signatures** exist in `docs/10-interfaces.md` and match the real upstream code.
   - **Acceptance criteria** are executable: named test functions, concrete inputs and expected outputs, commands with expected exit codes.
   - **Dependencies** are correct, and no task is bigger than about one focused session. Split it if it is.
   - Pitfalls specific to Windows, units, determinism, or data splits are written down.
5. Edit the phase file, `docs/10-interfaces.md`, and BACKLOG.md. Keep task IDs stable. New tasks get suffixes (`P3-02a`).
6. Append a dated entry to `docs/log/refinements.md`: what changed and why.
7. Commit as `docs(tasks): refine phase <n>`. Don't implement production code in this skill.
