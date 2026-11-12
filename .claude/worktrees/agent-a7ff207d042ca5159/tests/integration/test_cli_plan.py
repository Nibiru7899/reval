"""P4-09: `reval plan` on the mini project after a data edit."""

import json
from pathlib import Path

from typer.testing import CliRunner

from reval.cli.main import app
from reval.domain.plan import RevalidationPlan
from reval.services import Project

runner = CliRunner()


def _cli(root: Path, *args: str) -> tuple[int, str]:
    r = runner.invoke(app, [*args, "--project", str(root)])
    return r.exit_code, r.stdout


def _changed_project(root: Path) -> None:
    """Evidence for everything, then one measured temperature edited: `data` consumers become stale."""
    assert _cli(root, "run", "--all")[0] in (0, 1, 2)
    data = root / "data" / "data.csv"
    data.write_text(data.read_text(encoding="utf-8").replace("g1,0.0,19.5", "g1,0.0,19.6"), encoding="utf-8")


def test_plan_table_is_deterministic_and_stored(root: Path) -> None:
    _changed_project(root)
    code, out = _cli(root, "plan")
    assert code == 0, out
    assert "total cost" in out and "unrestorable:" in out and "deferred:" in out
    assert _cli(root, "plan")[1] == out
    proj = Project.open(root)
    assert proj.store.latest_plan(proj.snapshot().id) is not None


def test_plan_json_validates_as_revalidation_plan(root: Path) -> None:
    _changed_project(root)
    code, out = _cli(root, "plan", "--format", "json")
    assert code == 0, out
    plan = RevalidationPlan.model_validate_json(out)
    assert plan.solver_status == "OPTIMAL"
    assert plan.runs, "the data edit makes claims stale, so something must be rerun"
    assert json.loads(out)["id"] == plan.id


def test_budget_zero_defers_every_restorable_claim(root: Path) -> None:
    _changed_project(root)
    full = RevalidationPlan.model_validate_json(_cli(root, "plan", "--format", "json")[1])
    restorable = set(full.chosen_clauses) | set(full.deferred)
    zero = RevalidationPlan.model_validate_json(_cli(root, "plan", "--budget", "0", "--format", "json")[1])
    assert zero.objective == "max_restored"
    assert set(zero.deferred) == restorable
    assert zero.total_cost == 0


def test_greedy_and_all_planners_run(root: Path) -> None:
    _changed_project(root)
    for name in ("greedy", "all"):
        code, out = _cli(root, "plan", "--planner", name, "--format", "json")
        assert code == 0 and RevalidationPlan.model_validate_json(out).planner == name


def test_all_planner_with_budget_exits_3(root: Path) -> None:
    _changed_project(root)
    assert _cli(root, "plan", "--planner", "all", "--budget", "5")[0] == 3
