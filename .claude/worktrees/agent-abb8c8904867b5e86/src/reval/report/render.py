# ruff: noqa: E501  (inline HTML/CSS/SVG string literals)
"""Markdown and self-contained HTML renderings of a :class:`Report`. Pure: no clock, no I/O, no network.

Plain string building (jinja2 is not a dependency). Every dynamic value goes through ``html.escape``.
"""

from html import escape

from reval.report.model import Report, ReportClaim, ReportEvidence
from reval.report.styles import CSS, ICONS

STATUS_ORDER = ("supported", "waived", "stale", "inconclusive", "violated")
# Icon plus the word everywhere: no status is conveyed by a symbol or colour alone.
MD_ICON = {"supported": "✔", "waived": "✔", "stale": "⚠", "inconclusive": "?", "violated": "✖"}
LABEL = {
    "supported": "Supported",
    "waived": "Waived",
    "stale": "Stale",
    "inconclusive": "Inconclusive",
    "violated": "Violated",
}


def _n(x: float | None) -> str:
    return "-" if x is None else f"{x:.2f}"


def _interval(ev: ReportEvidence) -> str:
    if ev.interval is None:
        return f"point {_n(ev.point)}" if ev.point is not None else "-"
    return f"[{_n(ev.interval.lo)}, {_n(ev.interval.hi)}] {ev.interval.unit}"


def _limit(c: ReportClaim) -> str:
    return f"{c.op} {_n(c.limit)} {c.unit}"


def _headline(r: Report) -> str:
    total = sum(r.summary.values())
    ok = r.summary.get("supported", 0) + r.summary.get("waived", 0)
    if total == 0:
        return "The manifest declares no claims."
    if ok == total:
        return f"All {total} claims are supported by recorded evidence against their declared requirements."
    need = total - ok
    noun = "claim needs" if need == 1 else "claims need"
    return f"{ok} of {total} claims are supported by recorded evidence; {need} {noun} attention."


# ---------------------------------------------------------------------------------------- Markdown


def _md(cell: str) -> str:
    return cell.replace("|", "\\|").replace("\n", " ")


def _md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(_md(c) for c in row) + " |" for row in rows]
    return lines


def _md_status(status: str) -> str:
    return f"{MD_ICON[status]} {status.upper()}"


def render_markdown(r: Report) -> str:
    """Deterministic GitHub-flavoured Markdown; the disclaimer is the first paragraph."""
    out = [
        f"# Decision-validity report: {r.project}",
        "",
        f"_{r.disclaimer}_",
        "",
        f"**{_headline(r)}**",
        "",
        " · ".join(f"{LABEL[s]}: {r.summary.get(s, 0)}" for s in STATUS_ORDER),
        "",
        "## Claims",
        "",
    ]
    rows = [
        [
            c.id,
            _md_status(c.status),
            f"{c.requirement_id}: {c.quantity} {_limit(c)} ({c.criticality})",
            ", ".join(f"{x.code}" for x in c.reasons) or "-",
        ]
        for c in r.claims
    ]
    out += _md_table(["Claim", "Status", "Requirement", "Reasons"], rows)
    out += ["", "## Evidence", ""]
    for c in r.claims:
        out += [f"### {c.id}", ""]
        if not c.evidence:
            out += ["No evidence recorded for this claim.", ""]
            continue
        ev_rows = [
            [
                f"`{e.id[:12]}`",
                e.producer,
                e.verdict.upper(),
                e.freshness,
                _interval(e),
                f"{_limit(c)}",
            ]
            for e in c.evidence
        ]
        out += _md_table(["Evidence", "Producer", "Verdict", "Freshness", "Interval", "Limit"], ev_rows)
        out.append("")
    if r.changes:
        out += ["## Changes", ""]
        ch = [
            [
                c.kind.upper(),
                c.target,
                f"{c.old if c.old is not None else '-'} -> {c.new if c.new is not None else '-'}",
            ]
            for c in r.changes
        ]
        out += [*_md_table(["Kind", "Target", "Old -> new"], ch), ""]
    out += ["## Revalidation plan", ""]
    if r.plan is None:
        out += ["No plan is stored for this snapshot. Run `reval plan` to create one.", ""]
    else:
        p = r.plan
        budget = "none" if p.budget is None else f"{p.budget:g}"
        out += [
            f"Plan `{p.plan_id[:12]}`: planner {p.planner}, objective {p.objective}, budget {budget}, "
            f"solver {p.solver_status}, total cost {p.total_cost:g}.",
            "",
        ]
        if p.runs:
            out += _md_table(
                ["Producer", "Subject", "Cost", "Discharges"],
                [
                    [x.producer_id, x.subject_id, f"{x.cost:g}", ", ".join(x.discharges) or "-"]
                    for x in p.runs
                ],
            )
            out.append("")
        out += [
            f"Unrestorable: {', '.join(p.unrestorable) or '-'}",
            "",
            f"Deferred: {', '.join(p.deferred) or '-'}",
            "",
        ]
    out += [
        "## Hashes",
        "",
        f"- report_hash: `{r.report_hash}`",
        f"- report_id: `{r.report_id}`",
        f"- snapshot: `{r.snapshot_id}`",
        f"- git_rev: `{r.git_rev or '-'}`",
        f"- reval_version: {r.reval_version}",
        f"- created_at: {r.created_at}",
        "",
        f"_{r.disclaimer}_",
        "",
    ]
    return "\n".join(out)


# -------------------------------------------------------------------------------------------- HTML


def _badge(status: str, count: int | None = None) -> str:
    n = "" if count is None else f' <span class="n">{count}</span>'
    return (
        f'<span class="badge b-{status}"><svg aria-hidden="true"><use href="#i-{status}"/></svg>'
        f"{escape(LABEL[status])}{n}</span>"
    )


def _range_svg(c: ReportClaim, ev: ReportEvidence, lo: float, hi: float) -> str:
    """Interval of one evidence item on the claim's shared axis, with the declared limit drawn through it."""
    x0, x1 = 8.0, 392.0

    def x(v: float) -> float:
        return x0 + (v - lo) / (hi - lo) * (x1 - x0)

    parts = [f'<rect class="track" x="{x0}" y="14" width="{x1 - x0}" height="12" rx="2"/>']
    lx = x(c.limit)
    # Hatched = the side of the limit that would violate the requirement.
    if c.op == "<=":
        parts.append(f'<rect class="over" x="{lx:.1f}" y="14" width="{x1 - lx:.1f}" height="12"/>')
    else:
        parts.append(f'<rect class="over" x="{x0}" y="14" width="{lx - x0:.1f}" height="12"/>')
    if ev.interval is not None:
        a, b = x(ev.interval.lo), x(ev.interval.hi)
        parts.append(
            f'<rect class="iv {escape(ev.verdict)}" x="{a:.1f}" y="16" width="{max(b - a, 2.0):.1f}" height="8" rx="1"/>'
        )
    if ev.point is not None:
        parts.append(f'<circle class="pt" cx="{x(ev.point):.1f}" cy="20" r="3.6"/>')
    anchor = "end" if lx > (x0 + x1) / 2 else "start"
    tx = lx - 4 if anchor == "end" else lx + 4
    parts.append(f'<line class="lim" x1="{lx:.1f}" x2="{lx:.1f}" y1="8" y2="32"/>')
    parts.append(
        f'<text class="limt" x="{tx:.1f}" y="9" text-anchor="{anchor}">limit {escape(_n(c.limit))}</text>'
    )
    parts.append(f'<text x="{x0}" y="40" text-anchor="start">{escape(_n(lo))}</text>')
    parts.append(f'<text x="{x1}" y="40" text-anchor="end">{escape(_n(hi))} {escape(c.unit)}</text>')
    label = f"{ev.producer}: {_interval(ev)} against limit {_limit(c)}"
    return (
        f'<svg class="range" viewBox="0 0 400 44" role="img" aria-label="{escape(label)}" '
        f'preserveAspectRatio="xMidYMid meet">{"".join(parts)}</svg>'
    )


def _axis(c: ReportClaim) -> tuple[float, float]:
    vals = [c.limit]
    for e in c.evidence:
        if e.interval is not None:
            vals += [e.interval.lo, e.interval.hi]
        if e.point is not None:
            vals.append(e.point)
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.15 or abs(c.limit) * 0.05 or 1.0
    return lo - pad, hi + pad


def _claim_section(c: ReportClaim) -> str:
    lo, hi = _axis(c)
    out = [
        f'<section class="claim" id="claim-{escape(c.id)}" aria-labelledby="h-{escape(c.id)}">',
        f'<header><h3 id="h-{escape(c.id)}">{escape(c.id)}</h3>{_badge(c.status)}</header>',
        f'<p class="req">{escape(c.requirement)} <span class="mono">({escape(c.quantity)} {escape(_limit(c))}; '
        f"{escape(c.criticality)} criticality; subject {escape(c.subject)})</span></p>",
    ]
    if c.reasons:
        out.append('<ul class="reasons">')
        for r in c.reasons:
            out.append(f'<li><span class="code">{escape(r.code)}</span> {escape(r.message)}</li>')
        out.append("</ul>")
    if not c.evidence:
        out.append('<p class="none">No evidence recorded for this claim.</p>')
    for e in c.evidence:
        used = " Used in the satisfied clause." if e.used_in_clause else ""
        recorded = f", recorded {escape(e.recorded_verdict)}" if e.recorded_verdict else ""
        out.append(
            '<div class="ev">'
            f'<div class="who"><b>{escape(e.producer)}</b><br>'
            f'<span class="muted">{escape(e.producer_kind)} · verdict {escape(e.verdict.upper())}{recorded}'
            f" · {escape(e.freshness)}.{used}</span></div>"
            f"{_range_svg(c, e, lo, hi)}"
            f'<div class="vals">{escape(_interval(e))}<br><span class="muted mono">{escape(e.id[:12])}</span></div>'
            "</div>"
        )
    out.append("</section>")
    return "\n".join(out)


def render_html(r: Report) -> str:
    """One self-contained page: inline CSS and icons, no scripts, no external requests."""
    total = sum(r.summary.values()) or 1
    bar = "".join(
        f'<span class="s-{s}" style="flex:{r.summary.get(s, 0)}" title="{escape(LABEL[s])}: {r.summary.get(s, 0)}"></span>'
        for s in STATUS_ORDER
        if r.summary.get(s, 0)
    )
    legend = "".join(f"<li>{_badge(s, r.summary.get(s, 0))}</li>" for s in STATUS_ORDER)
    rows = []
    for c in r.claims:
        reasons = (
            "".join(f'<li><span class="code">{escape(x.code)}</span></li>' for x in c.reasons) or "<li>-</li>"
        )
        rows.append(
            f'<tr><th scope="row"><a href="#claim-{escape(c.id)}">{escape(c.id)}</a></th>'
            f"<td>{_badge(c.status)}</td>"
            f'<td>{escape(c.requirement_id)}<br><span class="muted mono">{escape(c.quantity)} {escape(_limit(c))}</span></td>'
            f"<td>{escape(c.criticality)}</td>"
            f'<td><ul class="reasons">{reasons}</ul></td></tr>'
        )
    changes = ""
    if r.changes:
        crow = "".join(
            f'<tr><td>{escape(c.kind.upper())}</td><td class="mono">{escape(c.target)}</td>'
            f"<td>{escape(str(c.old) if c.old is not None else '-')} → {escape(str(c.new) if c.new is not None else '-')}</td></tr>"
            for c in r.changes
        )
        changes = (
            '<h2>Changes</h2><div class="scroll"><table><caption>Changes between the compared snapshots</caption>'
            f"<thead><tr><th>Kind</th><th>Target</th><th>Old → new</th></tr></thead><tbody>{crow}</tbody></table></div>"
        )
    if r.plan is None:
        plan = '<p class="none">No plan is stored for this snapshot. Run <code>reval plan</code> to create one.</p>'
    else:
        p = r.plan
        budget = "none" if p.budget is None else f"{p.budget:g}"
        prow = "".join(
            f'<tr><td class="mono">{escape(x.producer_id)}</td><td>{escape(x.subject_id)}</td>'
            f'<td class="num">{x.cost:g}</td><td>{escape(", ".join(x.discharges) or "-")}</td></tr>'
            for x in p.runs
        )
        table = (
            '<div class="scroll"><table><caption>Planned runs, in execution order</caption><thead><tr><th>Producer</th><th>Subject</th>'
            f'<th class="num">Cost</th><th>Discharges</th></tr></thead><tbody>{prow}</tbody></table></div>'
            if p.runs
            else '<p class="none">The plan contains no runs.</p>'
        )
        plan = (
            f'<dl class="kv"><dt>Plan</dt><dd class="mono">{escape(p.plan_id[:12])}</dd>'
            f"<dt>Planner</dt><dd>{escape(p.planner)}, objective {escape(p.objective)}, budget {escape(budget)}, "
            f"solver {escape(p.solver_status)}</dd><dt>Total cost</dt><dd>{p.total_cost:g}</dd>"
            f"<dt>Unrestorable</dt><dd>{escape(', '.join(p.unrestorable) or '-')}</dd>"
            f"<dt>Deferred</dt><dd>{escape(', '.join(p.deferred) or '-')}</dd></dl>{table}"
        )
    hashes = "".join(
        f'<tr><th scope="row">{escape(k)}</th><td class="hash">{escape(v)}</td></tr>'
        for k, v in sorted(r.hashes.items())
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Decision-validity report: {escape(r.project)}</title>
<style>{CSS}</style>
</head>
<body>
{ICONS}
<main>
<header class="top">
<h1>Decision-validity report: {escape(r.project)}</h1>
<dl class="meta">
<div><dt>Snapshot</dt><dd class="mono">{escape(r.snapshot_id[:12])}</dd></div>
<div><dt>Revision</dt><dd class="mono">{escape((r.git_rev or "-")[:12])}</dd></div>
<div><dt>Created</dt><dd>{escape(r.created_at)}</dd></div>
<div><dt>ReVal</dt><dd>{escape(r.reval_version)}</dd></div>
</dl>
</header>
<p class="disclaimer" role="note">{escape(r.disclaimer)}</p>

<p class="verdict">{escape(_headline(r))}</p>
<div class="bar" role="img" aria-label="Claims by status: {escape(", ".join(f"{LABEL[s]} {r.summary.get(s, 0)}" for s in STATUS_ORDER))} of {total}">{bar}</div>
<ul class="legend">{legend}</ul>

<h2>Claims</h2>
<div class="scroll"><table>
<caption>Status of each claim against its declared requirement</caption>
<thead><tr><th>Claim</th><th>Status</th><th>Requirement</th><th>Criticality</th><th>Reasons</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table></div>

<h2>Evidence against limits</h2>
<p class="muted">Each bar is the evidence interval on the claim's own axis. The line is the declared limit; the hatched side would violate it. A hollow dot marks the point estimate.</p>
{"".join(_claim_section(c) for c in r.claims)}

{changes}
<h2>Revalidation plan</h2>
{plan}

<footer>
<h2 style="margin-top:0;border:0">Hashes</h2>
<dl class="kv">
<dt>report_hash</dt><dd class="hash">{escape(r.report_hash)}</dd>
<dt>report_id</dt><dd class="hash">{escape(r.report_id)}</dd>
<dt>snapshot</dt><dd class="hash">{escape(r.snapshot_id)}</dd>
<dt>git_rev</dt><dd class="hash">{escape(r.git_rev or "-")}</dd>
</dl>
<div class="scroll"><table><caption>Assessment input hash per claim</caption><thead><tr><th>Claim</th><th>input_hash</th></tr></thead><tbody>{hashes}</tbody></table></div>
<p class="disclaimer">{escape(r.disclaimer)}</p>
</footer>
</main>
</body>
</html>
"""
