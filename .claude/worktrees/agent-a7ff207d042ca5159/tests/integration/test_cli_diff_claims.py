"""P3-06: `reval diff` claim section and status-based exit codes."""

import json
from pathlib import Path

from tests.helpers.gitrepo import cli, make_repo


def test_diff_lists_affected_claims_and_exits_1(root: Path) -> None:
    make_repo(root, "1.05")
    r = cli(root, "diff", "HEAD~1", "HEAD")
    assert r.exit_code == 2, r.output  # C-S2-TEMP stays violated, which outranks stale (docs/09)
    rows = {ln.split()[0]: ln.split() for ln in r.stdout.splitlines() if ln.startswith("C-")}
    assert rows["C-SHAFT"][3] == "no"
    assert rows["C-S1-TEMP"][3] == "yes"
    assert "FIELD_CHANGED" in r.stdout


def test_diff_json_reports_affected_claims(root: Path) -> None:
    make_repo(root, "1.05")
    body = json.loads(cli(root, "diff", "HEAD~1", "HEAD", "--format", "json").stdout)
    assert "C-SHAFT" not in body["affected_claims"]
    assert "C-S1-TEMP" in body["affected_claims"]
    classes = {v["class"] for v in body["freshness"].values()}
    assert {"carry_forward", "invalidated", "fresh_exact"} <= classes
