"""`reval` command-line entry point. Commands are added per docs/09-api-and-ui.md as milestones land."""

import typer

from reval import __version__

app = typer.Typer(
    help="ReVal: which engineering conclusions survive a change, and the cheapest way to re-prove the rest.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """ReVal command-line interface."""


@app.command()
def version() -> None:
    """Print the installed ReVal version."""
    typer.echo(f"reval {__version__}")
