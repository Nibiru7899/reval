"""A temporary git repository around a copy of the mini project (for diff and freshness integration tests)."""

import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner, Result

from reval.cli.main import app

_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
}


def git(root: Path, *args: str) -> str:
    """Run git in ``root`` with a fixed identity; raise with stderr on failure."""
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **_ENV},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {args} failed: {proc.stderr}")
    return proc.stdout


def init_repo(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    (root / ".gitignore").write_text(".reval/\n__pycache__/\n", encoding="utf-8")


def commit_all(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


_runner = CliRunner()


def cli(root: Path, *args: str) -> Result:
    return _runner.invoke(app, [*args, "--project", str(root)])


def make_repo(root: Path, new_scale: str) -> Path:
    """Commit 1: lock + evidence from ``run --all``; commit 2: ``load.scale`` edited and re-locked."""
    init_repo(root)
    assert cli(root, "snapshot", "--write").exit_code == 0
    cli(root, "run", "--all")
    commit_all(root, "lock 1")
    params = root / "params" / "params.yaml"
    params.write_text(
        params.read_text(encoding="utf-8").replace("scale: 1.0", f"scale: {new_scale}"), encoding="utf-8"
    )
    assert cli(root, "snapshot", "--write").exit_code == 0
    commit_all(root, "lock 2")
    return root
