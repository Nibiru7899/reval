import threading

from fastapi import APIRouter, Depends, HTTPException

from reval.api.deps import AppState, get_project, get_state, require_default_project, resolve_snapshot
from reval.api.schemas import JobRef, PlanRequest
from reval.core.canonical import content_id
from reval.domain.plan import RevalidationPlan
from reval.services import Project
from reval.store import Job, JobState

router = APIRouter(prefix="/projects/{p}", dependencies=[Depends(require_default_project)], tags=["plans"])


@router.post("/plans", status_code=201)
def create_plan(body: PlanRequest, project: Project = Depends(get_project)) -> RevalidationPlan:  # noqa: B008
    """Plan the cheapest runs restoring stale or inconclusive claims (with a budget: maximise restored)."""
    snap = resolve_snapshot(project, body.snapshot) if body.snapshot is not None else None
    return project.plan(
        snap,
        planner=body.planner,
        objective="min_cost" if body.budget is None else "max_restored",
        budget=body.budget,
    )


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, project: Project = Depends(get_project)) -> RevalidationPlan:  # noqa: B008
    """A stored plan by id."""
    found = project.store.get_plan(plan_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"unknown plan {plan_id!r}")
    return found


def _new_job_id(project: Project, plan_id: str) -> str:
    attempt = 0
    while True:
        jid = content_id({"api_job": plan_id, "attempt": attempt})[:16]
        if project.store.get_job(jid) is None:
            return jid
        attempt += 1


def _execute_in_background(state: AppState, job_id: str, plan: RevalidationPlan) -> None:
    """Thread body. Holds the project lock for the whole run, so other project requests wait for it."""
    with state.lock:
        project = state.project()
        project.store.update_job_state(job_id, JobState.RUNNING)
        try:
            outcome = project.execute_plan(plan)
        except Exception as exc:  # any failure must end in a terminal job state, never a hung job
            project.store.update_job_state(
                job_id, JobState.FAILED, result={"error": f"{type(exc).__name__}: {exc}"}
            )
            return
        project.store.update_job_state(
            job_id,
            JobState.SUCCEEDED,
            result={
                "plan_id": plan.id,
                "evidence_ids": sorted(e.id for e in outcome.evidence),
                "run_job_ids": [j.id for j in outcome.jobs],
                "failed_runs": sum(1 for j in outcome.jobs if j.state is JobState.FAILED),
                "statuses": {k: v.status.value for k, v in sorted(outcome.after.items())},
            },
        )


@router.post("/plans/{plan_id}/execute", status_code=202)
def execute_plan(
    plan_id: str,
    project: Project = Depends(get_project),  # noqa: B008
    state: AppState = Depends(get_state),  # noqa: B008
) -> JobRef:
    """Start executing a stored plan in a background thread; poll ``get_job`` or stream its events."""
    plan = project.store.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"unknown plan {plan_id!r}")
    live = project.snapshot()
    if live.id != plan.snapshot_id:
        raise HTTPException(
            status_code=409,
            detail=f"plan {plan.id[:12]} was made for snapshot {plan.snapshot_id[:12]}, "
            f"but the working tree is at {live.id[:12]}; create a new plan",
        )
    job = Job(
        id=_new_job_id(project, plan.id),
        kind="run_plan",
        state=JobState.QUEUED,
        payload={"plan_id": plan.id, "total_runs": len(plan.runs)},
    )
    project.store.put_job(job)
    threading.Thread(target=_execute_in_background, args=(state, job.id, plan), daemon=True).start()
    return JobRef(job_id=job.id)
