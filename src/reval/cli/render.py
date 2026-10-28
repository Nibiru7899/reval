"""Human and machine renderings of assessments. Rich tables on a TTY, plain aligned text otherwise."""

import sys
from collections.abc import Mapping, Sequence

from rich.console import Console
from rich.table import Table

from reval.core.canonical import canonical_json
from reval.domain import ACCEPTED_STATUSES, Assessment, Change, Status
from reval.services import DiffReport

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


DISCLAIMER = (
    "ReVal reports the state of recorded evidence against declared requirements. It does not certify safety."
)


def _value(v: object) -> str:
    return "-" if v is None else str(v)


def _change_detail(c: Change) -> str:
    parts: list[str] = []
    if c.old is not None or c.new is not None:
        parts.append(f"{_value(c.old)} -> {_value(c.new)}")
    if c.delta is not None:
        parts.append(f"delta {c.delta:g}")
    if c.detail:
        parts.append(c.detail)
    return "; ".join(parts) if parts else "-"


def _change_rows(report: DiffReport) -> list[list[str]]:
    return [[c.kind.value.upper(), c.target, _change_detail(c)] for c in report.changes.changes]


def _claim_rows(report: DiffReport) -> list[list[str]]:
    rows: list[list[str]] = []
    for cid in sorted(report.after):
        after = report.after[cid]
        before = report.before.get(cid)
        rows.append(
            [
                cid,
                before.status.value.upper() if before else "-",
                after.status.value.upper(),
                "yes" if cid in report.affected_claims else "no",
                _reasons(after) or "-",
            ]
        )
    return rows


def diff_json(report: DiffReport) -> str:
    """``canonical_json`` of the whole report (freshness results flattened; nothing time-dependent)."""
    body = {
        "changes": report.changes,
        "freshness": {
            eid: {"class": fr.cls.value, "inflation": fr.inflation, "reasons": fr.reasons}
            for eid, fr in sorted(report.freshness.items())
        },
        "before": {k: report.before[k] for k in sorted(report.before)},
        "after": {k: report.after[k] for k in sorted(report.after)},
        "affected_claims": list(report.affected_claims),
    }
    return canonical_json(body).decode("utf-8")


def render_diff(report: DiffReport) -> str:
    """Change set and claim section as plain text (or a Rich table on a TTY, returning '')."""
    out: list[str] = []
    changes = _change_rows(report)
    if changes:
        text = _emit("Changes", ["KIND", "TARGET", "DETAIL"], changes, [])
        if text:
            out.append(text)
    else:
        out.append("no changes")
    claims = _claim_rows(report)
    if claims:
        text = _emit("Claims", ["CLAIM", "BEFORE", "AFTER", "AFFECTED", "REASONS"], claims, [1, 2])
        if text:
            out.append(text)
    return "\n\n".join(out)


# Status icon plus the word, so no status is signalled by a symbol alone.
_ICON = {
    Status.SUPPORTED: "✔",
    Status.WAIVED: "✔",
    Status.STALE: "⚠",
    Status.INCONCLUSIVE: "?",
    Status.VIOLATED: "✖",
}


def _md(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ")


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_md(c) for c in r) + " |" for r in rows]
    return lines


def _md_status(status: Status | None) -> str:
    return "-" if status is None else f"{_ICON[status]} {status.value.upper()}"


def render_diff_markdown(report: DiffReport) -> str:
    """GitHub-flavoured Markdown for PR comments. Deterministic: no timestamps, sorted rows."""
    need = [cid for cid, a in sorted(report.after.items()) if a.status not in ACCEPTED_STATUSES]
    n = len(need)
    noun = "claim needs" if n == 1 else "claims need"
    lines = [
        "## ReVal change impact",
        "",
        f"**{n} {noun} revalidation.** {len(report.affected_claims)} of {len(report.after)} claims affected "
        f"by {len(report.changes.changes)} change(s).",
        "",
        "### Changes",
        "",
    ]
    changes = _change_rows(report)
    lines += _md_table(["Kind", "Target", "Detail"], changes) if changes else ["No changes."]
    lines += ["", "### Claims", ""]
    claim_rows = [
        [
            cid,
            _md_status(report.before[cid].status if cid in report.before else None),
            _md_status(report.after[cid].status),
            "yes" if cid in report.affected_claims else "no",
            _reasons(report.after[cid]) or "-",
        ]
        for cid in sorted(report.after)
    ]
    lines += _md_table(["Claim", "Before", "After", "Affected", "Reasons"], claim_rows)
    lines += ["", f"_{DISCLAIMER}_", ""]
    return "\n".join(lines)
