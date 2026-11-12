"""P4-10/P4-11: `reval run --plan/--only`, the job runner and the automatic re-assessment."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

import reval.services.project as project_module
from reval.cli.main import app
from reval.domain import Status
from reval.errors import ProducerError
from reval.services import Project
from reval.store import JobState
from tests.integration.test_cli_plan import _changed_project

runner = CliRunner()


def _cli(root: Path, *args: str) -> tuple[int, str]:
    r = runner.invoke(app, [*args, "--project", str(root)])
    return r.exit_code, r.stdout


def _statuses(root: Path) -> dict[str, str]:
    proj = Project.open(root)
    return {c: a.status.value for c, a in proj.assess().items()}


def test_diff_plan_run_turns_stale_claims_supported(root: Path) -> None:
    _changed_project(root)
    before = _statuses(root)
    assert before["C-S1-TEMP"] == before["C-S1-HI"] == "stale"
    assert _cli(root, "plan")[0] == 0
    code, out = _cli(root, "run", "--plan", "latest")
    assert code == 2, out  # C-S2-TEMP stays violated
    rows = {ln.split()[0]: ln.split() for ln in out.splitlines() if ln.startswith("C-")}
    assert rows["C-S1-TEMP"][1:3] == ["STALE", "SUPPORTED"]
    assert rows["C-S1-HI"][1:3] == ["STALE", "SUPPORTED"]
    assert _statuses(root)["C-S1-TEMP"] == "supported"


def test_run_appends_evidence_and_assessment_batches(root: Path) -> None:
    _changed_project(root)
    proj = Project.open(root)
    n_evidence = len(proj.store.list_evidence())
    plan = proj.plan()
    outcome = proj.execute_plan(plan)
    assert len(Project.open(root).store.list_evidence()) == n_evidence + len(outcome.evidence)
    assert all(j.state is JobState.SUCCEEDED for j in outcome.jobs)
    stored = proj.store.get_job(outcome.jobs[0].id)
    assert stored is not None and stored.state is JobState.SUCCEEDED and stored.result is not None
    assert outcome.before["C-S1-TEMP"].status is Status.STALE
    assert outcome.after["C-S1-TEMP"].status is Status.SUPPORTED


def test_failing_producer_gives_failed_job_and_claim_stays_stale(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _changed_project(root)
    proj = Project.open(root)
    plan = proj.plan()
    n_evidence = len(proj.store.list_evidence())

    def boom(*args: object, **kwargs: object) -> None:
        raise ProducerError("simulated crash")

    monkeypatch.setattr(project_module, "run_producer", boom)
    outcome = proj.execute_plan(plan)
    assert [j.state for j in outcome.jobs] == [JobState.FAILED] * len(plan.runs)
    assert "simulated crash" in str((outcome.jobs[0].result or {}).get("error"))
    assert len(proj.store.list_evidence()) == n_evidence
    assert outcome.after["C-S1-TEMP"].status is Status.STALE


def test_runner_continues_after_a_failed_run(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _changed_project(root)
    proj = Project.open(root)
    plan = proj.plan(planner="all")
    assert len(plan.runs) >= 2
    real = project_module.run_producer
    first = plan.runs[0].producer_id

    def flaky(registry, pid, *args, **kwargs):  # type: ignore[no-untyped-def]
        if pid == first:
            raise ProducerError("boom")
        return real(registry, pid, *args, **kwargs)

    monkeypatch.setattr(project_module, "run_producer", flaky)
    states = [j.state for j in proj.execute_plan(plan).jobs]
    assert states[0] is JobState.FAILED and JobState.SUCCEEDED in states


def test_only_filters_runs_and_rejects_unknown_producer(root: Path) -> None:
    _changed_project(root)
    assert _cli(root, "plan", "--planner", "all")[0] == 0
    code, out = _cli(root, "run", "--plan", "latest", "--only", "mini.producers:shaft_check")
    assert "ran 0 planned runs" in out
    assert code == 2
    assert _cli(root, "run", "--plan", "latest", "--only", "nope")[0] == 3


def test_plan_for_other_snapshot_is_refused(root: Path) -> None:
    _changed_project(root)
    proj = Project.open(root)
    plan = proj.plan()
    params = root / "params" / "params.yaml"
    params.write_text(params.read_text(encoding="utf-8").replace("gain: 2.0", "gain: 1.9"), encoding="utf-8")
    assert _cli(root, "run", "--plan", plan.id)[0] == 3
    assert _cli(root, "run", "--plan", "latest")[0] == 3  # no plan stored for the new snapshot


def test_run_all_and_plan_are_exclusive(root: Path) -> None:
    assert _cli(root, "run", "--all", "--plan", "latest")[0] == 3
