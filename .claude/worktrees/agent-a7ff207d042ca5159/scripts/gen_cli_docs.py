"""Generate docs/site/cli.md from the live Typer app (`reval --help` and every subcommand's help).

The reference is never hand-typed: rerun this script after changing the CLI.
    .venv/Scripts/python scripts/gen_cli_docs.py          # write docs/site/cli.md
    .venv/Scripts/python scripts/gen_cli_docs.py --check  # exit 1 if the file is out of date
"""

import sys
from pathlib import Path
from typing import Any

import typer.main
from typer.testing import CliRunner

OUT = Path(__file__).resolve().parents[1] / "docs" / "site" / "cli.md"

HEADER = """# CLI reference

!!! note "Generated"
    This page is generated from the live Typer app by `scripts/gen_cli_docs.py`. Do not edit it by hand.

**Exit codes** (shared by `status`, `run` and `diff`): `0` every claim accepted, `1` some claim stale or
inconclusive, `2` some claim violated, `3` error. A non-zero exit is a signal, not a crash.

Every command takes `--project <path>` (default: the current directory).
"""

# Rich draws unicode boxes on most terminals and ASCII on legacy Windows consoles; normalise to ASCII.
_ASCII_BOX = str.maketrans({"┌": "+", "┐": "+", "└": "+", "┘": "+", "─": "-", "│": "|"})


def _help(args: list[str]) -> str:
    """The `--help` text of one command, at a fixed width and without colour."""
    from reval.cli.main import app

    env = {"COLUMNS": "80", "NO_COLOR": "1", "TERM": "dumb"}
    result = CliRunner().invoke(app, [*args, "--help"], env=env, color=False, prog_name="reval")
    text = result.output.translate(_ASCII_BOX)
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines())


def _walk(cmd: Any, path: list[str]) -> list[list[str]]:
    out = [path]
    # typer vendors its own click, so test for sub-commands by duck typing.
    if getattr(cmd, "commands", None):
        for name, sub in cmd.commands.items():
            out.extend(_walk(sub, [*path, name]))
    return out


def render() -> str:
    """The whole page as Markdown."""
    from reval.cli.main import app

    root = typer.main.get_command(app)
    parts = [HEADER]
    for path in _walk(root, []):
        title = "reval" if not path else "reval " + " ".join(path)
        level = "##" if len(path) <= 1 else "###"
        parts.append(f"{level} `{title}`\n\n```text\n{_help(path)}\n```\n")
    return "\n".join(parts)


def main() -> int:
    """Write the page, or with --check compare it with the file on disk."""
    text = render() + "\n"
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        return 0 if current == text else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
