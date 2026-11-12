"""P2-18: `reval run --all` reproduces EXPECTED.md and never duplicates evidence."""

from pathlib import Path

from typer.testing import CliRunner, Result

from reval.cli.main import app
from reval.services import Project

runner = CliRunner()


def _cli(root: Path, *args: str) -> Result:
    return runner.invoke(app, [*args, "--project", str(root)])


def _rows(stdout: str) -> dict[str, list[str]]:
    return {ln.split()[0]: ln.split() for ln in stdout.splitlines() if ln.startswith("C-")}


def test_run_all_then_status_reproduces_expected(root: Path) -> None:
    assert _cli(root, "snapshot", "--write").exit_code == 0
    r = _cli(root, "run", "--all")
    assert r.exit_code == 2, r.output  # C-S2-TEMP is violated (EXPECTED.md)
    rows = _rows(r.stdout)
    assert rows["C-S1-TEMP"][1:3] == ["INCONCLUSIVE", "SUPPORTED"]
    assert rows["C-S2-TEMP"][2] == "VIOLATED"
    s = _cli(root, "status")
    assert s.exit_code == 2
    assert {c: v[1] for c, v in _rows(s.stdout).items()} == {
        "C-S1-TEMP": "SUPPORTED",
        "C-S2-TEMP": "VIOLATED",
        "C-S1-HI": "SUPPORTED",
        "C-SHAFT": "SUPPORTED",
    }


def test_run_all_twice_adds_no_duplicate_evidence(root: Path) -> None:
    _cli(root, "run", "--all")
    n = len(Project.open(root).store.list_evidence())
    _cli(root, "run", "--all")
    assert len(Project.open(root).store.list_evidence()) == n == 6


def test_run_without_all_exits_3(root: Path) -> None:
    assert _cli(root, "run").exit_code == 3
