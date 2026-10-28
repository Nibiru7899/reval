"""Human and machine renderings of assessments. Rich tables on a TTY, plain aligned text otherwise."""

import sys
from collections.abc import Mapping, Sequence

from rich.console import Console
from rich.table import Table

from reval.core.canonical import canonical_json
from reval.domain import ACCEPTED_STATUSES, Assessment, Status

# Text labels carry the meaning; colour is decoration only (no status by colour alone).
_STYLE = {
    Status.SUPPORTED: "green",
    Status.WAIVED: "cyan",
    Status.STALE: "yellow",
    Status.INCONCLUSIVE: "yellow",
    Status.VIOLATED: "red bold",
}


def exit_code(assessments: Sequence[Assessment]) -> int:
    """docs/09: 0 all accepted, 1 some stale/inconclusive, 2 some violated."""
    statuses = {a.status for a in assessments}
    if Status.VIOLATED in statuses:
        return 2
    if statuses - ACCEPTED_STATUSES:
        return 1
    return 0


def _reasons(a: Assessment) -> str:
    return ", ".join(sorted({r.code.value for r in a.reasons}))


def _clause(a: Assessment) -> str:
    return "-" if a.satisfied_clause is None else str(a.satisfied_clause)


def status_json(snapshot_id: str, assessments: Mapping[str, Assessment]) -> str:
    """``canonical_json`` of ``{"assessments": [...], "snapshot_id": ...}``, claims sorted by id."""
    body = {"snapshot_id": snapshot_id, "assessments": [assessments[k] for k in sorted(assessments)]}
    return canonical_json(body).decode("utf-8")


def _plain(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)).rstrip()]
    lines += ["  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip() for r in rows]
    return "\n".join(lines)


def _emit(
    title: str, headers: Sequence[str], rows: Sequence[Sequence[str]], status_cols: Sequence[int]
) -> str:
    """Return plain text when stdout is not a TTY; on a TTY print a Rich table and return ''."""
    if not sys.stdout.isatty():
        return _plain(headers, rows)
    table = Table(title=title)
    for h in headers:
        table.add_column(h)
    for r in rows:
        cells = list(r)
        for i in status_cols:
            style = _STYLE.get(Status(cells[i].lower()), "") if cells[i] != "-" else ""
            cells[i] = f"[{style}]{cells[i]}[/]" if style else cells[i]
        table.add_row(*cells)
    Console().print(table)
    return ""


def render_status(snapshot_id: str, assessments: Mapping[str, Assessment]) -> str:
    rows = [
        [cid, assessments[cid].status.value.upper(), _clause(assessments[cid]), _reasons(assessments[cid])]
        for cid in sorted(assessments)
    ]
    return _emit(f"Claims @ {snapshot_id[:12]}", ["CLAIM", "STATUS", "CLAUSE", "REASONS"], rows, [1])


def render_before_after(before: Mapping[str, Assessment], after: Mapping[str, Assessment]) -> str:
    rows = [
        [
            cid,
            before[cid].status.value.upper() if cid in before else "-",
            after[cid].status.value.upper(),
            _clause(after[cid]),
        ]
        for cid in sorted(after)
    ]
    return _emit("Before / after", ["CLAIM", "BEFORE", "AFTER", "CLAUSE"], rows, [1, 2])
