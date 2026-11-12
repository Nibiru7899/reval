"""P3-02: `reval diff` prints the change set between two committed locks."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from reval.cli.main import app
from reval.errors import GitError, LockNotFoundError
from reval.gitio import read_file_at_rev, resolve_rev, snapshot_at_rev
from tests.helpers.gitrepo import commit_all, git, init_repo

runner = CliRunner()


def _cli(root: Path, *args: str) -> Result:
    return runner.invoke(app, [*args, "--project", str(root)])


@pytest.fixture
def repo(root: Path) -> Path:
    """Two commits: the lock at scale 1.0, then at scale 1.05 (no evidence needed here)."""
    init_repo(root)
    # an initial commit without a lock, to test the missing-lock path
    (root / "README.txt").write_text("x\n", encoding="utf-8")
    git(root, "add", "README.txt", ".gitignore")
    git(root, "commit", "-q", "-m", "init")
    assert _cli(root, "snapshot", "--write").exit_code == 0
    commit_all(root, "lock 1")
    params = root / "params" / "params.yaml"
    params.write_text(
        params.read_text(encoding="utf-8").replace("scale: 1.0", "scale: 1.05"), encoding="utf-8"
    )
    assert _cli(root, "snapshot", "--write").exit_code == 0
    commit_all(root, "lock 2")
    return root


def test_diff_json_has_single_field_change(repo: Path) -> None:
    r = _cli(repo, "diff", "HEAD~1", "HEAD", "--format", "json")
    assert r.exit_code in (0, 1), r.output  # exit code reflects claim statuses since P3-06
    body = json.loads(r.stdout)
    changes = body["changes"]["changes"]
    assert [(c["kind"], c["target"]) for c in changes] == [("field_changed", "params#/load/scale")]


def test_diff_against_working_tree_is_empty_when_clean(repo: Path) -> None:
    r = _cli(repo, "diff", "HEAD", "--format", "json")
    assert json.loads(r.stdout)["changes"]["changes"] == []


def test_revision_without_lock_exits_3(repo: Path) -> None:
    r = _cli(repo, "diff", "HEAD~2", "HEAD")
    assert r.exit_code == 3
    assert "error:" in r.output


def test_unknown_revision_exits_3(repo: Path) -> None:
    assert _cli(repo, "diff", "no-such-rev").exit_code == 3


def test_git_helpers(repo: Path) -> None:
    sha = resolve_rev(repo, "HEAD")
    assert len(sha) == 40
    snap = snapshot_at_rev(repo, "HEAD~1")
    assert snap.git_rev == resolve_rev(repo, "HEAD~1")
    assert snapshot_at_rev(repo, "HEAD").id != snap.id
    assert read_file_at_rev(repo, "HEAD", "README.txt").strip() == b"x"
    with pytest.raises(LockNotFoundError):
        snapshot_at_rev(repo, "HEAD~2")
    with pytest.raises(GitError):
        read_file_at_rev(repo, "HEAD", "nope.txt")
    with pytest.raises(GitError):
        resolve_rev(repo, "--output=x")
