"""P2-17: `reval snapshot` and `reval status` through typer's CliRunner."""

import json
from pathlib import Path

from typer.testing import CliRunner, Result

from reval.cli.main import app
from reval.core.canonical import canonical_json
from reval.domain import Assessment, Status
from reval.gitio import LOCK_FILE
from reval.services import Project

runner = CliRunner()


def _cli(root: Path, *args: str) -> Result:
    return runner.invoke(app, [*args, "--project", str(root)])


def _bump_scale(root: Path) -> None:
    params = root / "params" / "params.yaml"
    params.write_text(
        params.read_text(encoding="utf-8").replace("scale: 1.0", "scale: 1.2"), encoding="utf-8"
    )


def test_snapshot_write_is_deterministic(root: Path) -> None:
    r = _cli(root, "snapshot", "--write")
    assert r.exit_code == 0, r.output
    first = (root / LOCK_FILE).read_bytes()
    assert _cli(root, "snapshot", "--write").exit_code == 0
    assert (root / LOCK_FILE).read_bytes() == first


def test_snapshot_check(root: Path) -> None:
    assert _cli(root, "snapshot", "--check").exit_code == 1  # no lock yet
    _cli(root, "snapshot", "--write")
    assert _cli(root, "snapshot", "--check").exit_code == 0
    _bump_scale(root)
    assert _cli(root, "snapshot", "--check").exit_code == 1


def test_snapshot_write_and_check_conflict(root: Path) -> None:
    assert _cli(root, "snapshot", "--write", "--check").exit_code == 3


def test_status_without_evidence_is_inconclusive(root: Path) -> None:
    r = _cli(root, "status")
    assert r.exit_code == 1
    assert "INCONCLUSIVE" in r.stdout and "C-SHAFT" in r.stdout


def test_status_json_round_trips_and_violated_exits_2(root: Path) -> None:
    Project.open(root).run_all()
    r = _cli(root, "status", "--format", "json")
    assert r.exit_code == 2  # C-S2-TEMP is violated
    body = json.loads(r.stdout)
    assessments = [Assessment.model_validate(a) for a in body["assessments"]]
    assert {a.claim_id: a.status for a in assessments}["C-S2-TEMP"] is Status.VIOLATED
    assert r.stdout.strip().encode() == canonical_json(body)


def test_status_single_claim_all_accepted_exits_0(root: Path) -> None:
    Project.open(root).run_all()
    r = _cli(root, "status", "--claim", "C-SHAFT")
    assert r.exit_code == 0 and "SUPPORTED" in r.stdout
    assert _cli(root, "status", "--claim", "NOPE").exit_code == 3


def test_broken_manifest_exits_3_with_one_line(root: Path) -> None:
    (root / "reval.yaml").write_text("version: 1\nproject: [oops\n", encoding="utf-8")
    r = _cli(root, "status")
    assert r.exit_code == 3
    assert r.stderr.strip().count("\n") == 0 and r.stderr.startswith("error:")
    assert "Traceback" not in r.output


def test_status_warns_when_lock_is_stale(root: Path) -> None:
    _cli(root, "snapshot", "--write")
    _bump_scale(root)
    assert "warning" in _cli(root, "status").stderr
