"""P7-03: the 'add ReVal to a new project' tutorial, executed end to end on examples/beam_toy.

Mirrors docs/site/tutorial-new-project.md: start from an empty folder, `reval init`, drop in the manifest,
producers and data, lock, run, change a parameter, then diff, plan, run the plan and report.
"""

import json
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from reval.sdk import DEFAULT_REGISTRY
from tests.helpers.gitrepo import cli, commit_all, init_repo

BEAM_SRC = Path(__file__).resolve().parents[2] / "examples" / "beam_toy"


def _drop_beam() -> None:
    for name in [m for m in sys.modules if m == "beam" or m.startswith("beam.")]:
        del sys.modules[name]


@pytest.fixture
def proj(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "beam"
    root.mkdir()
    _drop_beam()
    DEFAULT_REGISTRY.clear()
    yield root
    _drop_beam()
    sys.path[:] = [p for p in sys.path if p != str(root.resolve())]
    DEFAULT_REGISTRY.clear()


def _statuses(root: Path) -> dict[str, str]:
    out = cli(root, "report", "--json")
    claims = json.loads(out.output)["claims"]
    return {c["id"]: c["status"] for c in claims}


def test_tutorial_end_to_end(proj: Path) -> None:
    init_repo(proj)
    assert cli(proj, "init").exit_code == 0  # starter manifest + .reval/
    shutil.copy(BEAM_SRC / "reval.yaml", proj / "reval.yaml")  # the tutorial replaces the starter manifest
    for sub in ("beam", "params", "inputs", "fitted"):
        shutil.copytree(BEAM_SRC / sub, proj / sub, ignore=shutil.ignore_patterns("__pycache__"))

    assert cli(proj, "snapshot", "--write").exit_code == 0
    assert cli(proj, "status").exit_code == 1  # nothing run yet: INCONCLUSIVE
    assert cli(proj, "run", "--all").exit_code == 0
    assert cli(proj, "status").exit_code == 0
    commit_all(proj, "baseline")

    params = proj / "params" / "beam.yaml"
    params.write_text(
        params.read_text(encoding="utf-8").replace("load_N: 600", "load_N: 700"), encoding="utf-8"
    )
    assert cli(proj, "snapshot", "--write").exit_code == 0
    commit_all(proj, "load 600 -> 700 N")

    diff = cli(proj, "diff", "HEAD~1", "HEAD")
    assert diff.exit_code == 1, diff.output
    assert "params#/beam/load_N" in diff.output
    assert "STALE" in diff.output

    plan = cli(proj, "plan")
    assert plan.exit_code == 0, plan.output
    # One analytic run (cost 2) restores both claims; surrogate (0.5) + analytic (2) would cost more.
    assert "beam_analytic" in plan.output
    assert "beam_surrogate" not in plan.output

    # 700 N pushes the analytic deflection past 15 mm, so re-proving ends in VIOLATED (exit 2), not SUPPORTED.
    run = cli(proj, "run", "--plan", "latest")
    assert run.exit_code == 2, run.output
    st = _statuses(proj)
    assert st == {"C-DEFL": "violated", "C-STRESS": "supported"}

    report = cli(proj, "report")
    assert report.exit_code == 0
    assert "does not certify safety" in report.output
