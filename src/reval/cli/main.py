"""`reval` command-line entry point. Commands are added per docs/09-api-and-ui.md as milestones land."""

import contextlib
import json
import sys
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from reval import __version__
from reval.cli import render
from reval.core.graph import EvidenceGraph
from reval.errors import LockNotFoundError, RevalError
from reval.gitio import LOCK_FILE, read_lock, snapshot_at_rev
from reval.gitio.git import repo_subdir
from reval.services import Project
from reval.services.project import MANIFEST_FILE

app = typer.Typer(
    help="ReVal: which engineering conclusions survive a change, and the cheapest way to re-prove the rest.",
    no_args_is_help=True,
)

ProjectOpt = Annotated[Path, typer.Option("--project", help="Project root (default: current directory).")]


def _guard(fn: Callable[..., None]) -> Callable[..., None]:
    """Map every RevalError to exit code 3 with a one-line message (docs/09)."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            fn(*args, **kwargs)
        except RevalError as exc:
            typer.echo(f"error: {' '.join(str(exc).split())}", err=True)
            raise typer.Exit(3) from exc

    return wrapper


@app.callback()
def main() -> None:
    """ReVal command-line interface."""


@app.command()
def version() -> None:
    """Print the installed ReVal version."""
    typer.echo(f"reval {__version__}")


@app.command()
@_guard
def snapshot(
    project: ProjectOpt = Path(),
    write: Annotated[bool, typer.Option("--write", help=f"Write {LOCK_FILE}.")] = False,
    check: Annotated[
        bool, typer.Option("--check", help="Exit 1 if the lock differs from the live state.")
    ] = False,
) -> None:
    """Compute the working-tree snapshot; optionally write or check the lock file."""
    if write and check:
        raise RevalError("--write and --check are mutually exclusive")
    proj = Project.open(project)
    snap = proj.snapshot(write_lock=write)
    typer.echo(f"snapshot {snap.id}")
    if write:
        typer.echo(f"wrote {proj.root / LOCK_FILE}")
    if check:
        try:
            committed = read_lock(proj.root / LOCK_FILE)
        except LockNotFoundError:
            typer.echo(f"{LOCK_FILE} not found; run `reval snapshot --write`", err=True)
            raise typer.Exit(1) from None
        if committed.id != snap.id:
            typer.echo(
                f"{LOCK_FILE} is out of date (lock {committed.id[:12]} != live {snap.id[:12]})", err=True
            )
            raise typer.Exit(1)
        typer.echo("lock is up to date")


def _warn_if_lock_differs(proj: Project, live_id: str) -> None:
    try:
        committed = read_lock(proj.root / LOCK_FILE)
    except RevalError:
        return
    if committed.id != live_id:
        typer.echo(f"warning: working tree differs from {LOCK_FILE}", err=True)


@app.command()
@_guard
def status(
    project: ProjectOpt = Path(),
    format: Annotated[Literal["table", "json"], typer.Option("--format", help="table or json")] = "table",
    claim: Annotated[str | None, typer.Option("--claim", help="Show only this claim.")] = None,
) -> None:
    """Assess every claim. Exit 0 all accepted, 1 stale or inconclusive, 2 violated, 3 error."""
    proj = Project.open(project)
    snap = proj.snapshot()
    _warn_if_lock_differs(proj, snap.id)
    assessments = proj.assess(snap)
    if claim is not None:
        if claim not in assessments:
            raise RevalError(f"unknown claim {claim!r}")
        assessments = {claim: assessments[claim]}
    if format == "json":
        typer.echo(render.status_json(snap.id, assessments))
    else:
        text = render.render_status(snap.id, assessments)
        if text:
            typer.echo(text)
    code = render.exit_code(list(assessments.values()))
    if code:
        raise typer.Exit(code)


@app.command()
@_guard
def plan(
    project: ProjectOpt = Path(),
    budget: Annotated[
        float | None, typer.Option("--budget", help="Cost budget; maximizes restored criticality within it.")
    ] = None,
    planner: Annotated[
        Literal["ilp", "greedy", "all"], typer.Option("--planner", help="ilp, greedy or all")
    ] = "ilp",
    format: Annotated[Literal["table", "json"], typer.Option("--format", help="table or json")] = "table",
) -> None:
    """Plan the cheapest runs that restore stale or inconclusive claims (stored, nothing is run)."""
    proj = Project.open(project)
    result = proj.plan(
        planner=planner,
        objective="min_cost" if budget is None else "max_restored",
        budget=budget,
    )
    if format == "json":
        typer.echo(render.plan_json(result))
    else:
        typer.echo(render.render_plan(result))


def _run_plan(proj: Project, plan_ref: str | None, only: str | None) -> None:
    snap = proj.snapshot()
    if plan_ref is None or plan_ref == "latest":
        chosen = proj.store.latest_plan(snap.id)
        if chosen is None:
            raise RevalError("no stored plan for the current snapshot; run `reval plan` first")
    else:
        chosen = proj.store.get_plan(plan_ref)
        if chosen is None:
            raise RevalError(f"unknown plan {plan_ref!r}")
    outcome = proj.execute_plan(chosen, only=only)
    failed = sum(1 for j in outcome.jobs if j.state.value == "failed")
    typer.echo(
        f"ran {len(outcome.jobs)} planned runs ({failed} failed), {len(outcome.evidence)} evidence items"
    )
    for text in (render.render_jobs(outcome.jobs), render.render_before_after(outcome.before, outcome.after)):
        if text:
            typer.echo(text)
    code = render.exit_code(list(outcome.after.values()))
    if code:
        raise typer.Exit(code)


@app.command()
@_guard
def run(
    project: ProjectOpt = Path(),
    all_: Annotated[
        bool, typer.Option("--all", help="Run every producer on every subject it is available for.")
    ] = False,
    plan_ref: Annotated[
        str | None, typer.Option("--plan", help="Run a stored plan's runs: a plan id or 'latest'.")
    ] = None,
    only: Annotated[
        str | None, typer.Option("--only", help="With --plan: run only this producer's planned runs.")
    ] = None,
) -> None:
    """Execute producers, store the evidence (append-only) and re-assess."""
    if all_ and (plan_ref is not None or only is not None):
        raise RevalError("--all cannot be combined with --plan or --only")
    if not all_ and plan_ref is None and only is None:
        raise RevalError("nothing to run; pass --all or --plan ID|latest [--only PRODUCER]")
    proj = Project.open(project)
    if not all_:
        _run_plan(proj, plan_ref, only)  # --only alone means: the latest plan
        return
    before = proj.assess()
    evidence = proj.run_all()
    after = proj.assess()
    typer.echo(f"ran {len(evidence)} producer results")
    text = render.render_before_after(before, after)
    if text:
        typer.echo(text)
    code = render.exit_code(list(after.values()))
    if code:
        raise typer.Exit(code)


@app.command()
@_guard
def diff(
    a: Annotated[str, typer.Argument(help="Base revision.")],
    b: Annotated[str | None, typer.Argument(help="Second revision (default: the working tree).")] = None,
    project: ProjectOpt = Path(),
    format: Annotated[
        Literal["table", "json", "markdown"], typer.Option("--format", help="table, json or markdown")
    ] = "table",
) -> None:
    """Change set, evidence freshness and affected claims between revisions (reads reval.lock.json)."""
    proj = Project.open(project)
    repo_root, subdir = repo_subdir(proj.root)
    old = snapshot_at_rev(repo_root, a, subdir)
    new = snapshot_at_rev(repo_root, b, subdir) if b is not None else proj.snapshot()
    report = proj.diff(old, new)
    if format == "json":
        typer.echo(render.diff_json(report))
    elif format == "markdown":
        # Markdown carries non-ASCII status icons; a legacy console codepage must not crash the command.
        with contextlib.suppress(AttributeError, ValueError):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        typer.echo(render.render_diff_markdown(report), nl=False)
    else:
        text = render.render_diff(report)
        if text:
            typer.echo(text)
    code = render.exit_code(list(report.after.values()))
    if code:
        raise typer.Exit(code)


_TEMPLATE = Path(__file__).parent / "templates" / "reval.yaml.tmpl"


@app.command()
@_guard
def init(project: ProjectOpt = Path()) -> None:
    """Write a commented starter reval.yaml and create the .reval/ store (never overwrites a manifest)."""
    root = project.resolve()
    manifest = root / MANIFEST_FILE
    if manifest.exists():
        raise RevalError(f"{manifest} already exists; refusing to overwrite it")
    root.mkdir(parents=True, exist_ok=True)
    manifest.write_text(_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    (root / ".reval").mkdir(exist_ok=True)
    typer.echo(f"wrote {manifest}")
    typer.echo("created .reval/ (add it to .gitignore)")


@app.command()
@_guard
def graph(
    out: Annotated[Path, typer.Option("--out", help="Where to write the graph JSON.")],
    project: ProjectOpt = Path(),
    claim: Annotated[
        str | None, typer.Option("--claim", help="Keep only this claim's cone and what it influences.")
    ] = None,
) -> None:
    """Export the evidence graph of the working-tree snapshot as JSON (nodes and edges)."""
    proj = Project.open(project)
    snap = proj.snapshot()
    if claim is not None and claim not in snap.claims:
        raise RevalError(f"unknown claim {claim!r}")
    g = EvidenceGraph.build(snap, proj.store.list_evidence())
    body = g.to_json(f"claim:{claim}" if claim is not None else None)
    out.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    typer.echo(f"wrote {out} ({len(body['nodes'])} nodes, {len(body['edges'])} edges)")
