"""Check docs/tasks: each phase-file task has a matching BACKLOG.md row; deps exist; no cycles.

Usage: python scripts/check_backlog.py   (exit code 1 on any problem). Read-only: statuses are never touched.
"""

import re
import sys
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

TASKS = Path(__file__).resolve().parent.parent / "docs" / "tasks"
HEADER = re.compile(
    r"^## (P\d-\d+) — (.+)\n- \*\*Owner:\*\* (.+?) · \*\*Depends on:\*\* (.+?) · \*\*Read first:\*\*", re.M
)
ROW = re.compile(r"^\| (P\d-\d+) \| (.+?) \| (.+?) \| (.+?) \| (\w[\w-]*) \|$", re.M)
STATUSES = {"todo", "in-progress", "review", "done", "blocked"}
# Cross-phase dependencies that are deliberate (justified in BACKLOG.md).
ALLOWED_LATER_PHASE = {("P0-05", "P1-01"), ("P0-06", "P1-02"), ("P1-01", "P2-01"), ("P1-06", "P2-01")}


def _deps(text: str) -> list[str]:
    return [] if text.strip() == "—" else [d.strip() for d in text.split(",")]


def _owner(text: str) -> str:
    # The phase files may add a parenthetical note ("human (sonnet can assist)"); compare the base owner only.
    return text.split(" (")[0].strip()


def main() -> int:
    errors: list[str] = []
    specs: dict[str, tuple[str, str, list[str]]] = {}
    for path in sorted(TASKS.glob("phase-*.md")):
        text = path.read_text(encoding="utf-8")
        headings = re.findall(r"^## P\d-\d+", text, re.M)
        found = HEADER.findall(text)
        if len(headings) != len(found):
            errors.append(f"{path.name}: {len(headings)} headings, {len(found)} parseable header lines")
        for tid, title, owner, deps in found:
            if tid in specs:
                errors.append(f"duplicate task id {tid}")
            specs[tid] = (title.strip(), _owner(owner), _deps(deps))

    rows = {m[0]: m for m in ROW.findall((TASKS / "BACKLOG.md").read_text(encoding="utf-8"))}
    for tid, (title, owner, deps) in specs.items():
        if tid not in rows:
            errors.append(f"{tid} missing from BACKLOG.md")
            continue
        _, r_title, r_owner, r_deps, status = rows[tid]
        if (r_title.strip(), _owner(r_owner), _deps(r_deps)) != (title, owner, deps):
            errors.append(f"{tid}: BACKLOG row differs from its phase file")
        if status not in STATUSES:
            errors.append(f"{tid}: unknown status {status!r}")
        for dep in deps:
            if dep not in specs:
                errors.append(f"{tid}: unknown dependency {dep}")
            elif dep[1] > tid[1] and (tid, dep) not in ALLOWED_LATER_PHASE:
                errors.append(f"{tid}: depends on later-phase task {dep}")
    errors += [f"{tid} in BACKLOG.md but in no phase file" for tid in rows.keys() - specs.keys()]

    try:
        tuple(TopologicalSorter({t: s[2] for t, s in specs.items()}).static_order())
    except CycleError as exc:
        errors.append(f"dependency cycle: {exc.args[1]}")

    for e in errors:
        print(e)
    print(f"tasks={len(specs)} errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
