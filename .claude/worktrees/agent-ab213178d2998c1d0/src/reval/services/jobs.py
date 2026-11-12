"""In-process job runner for planned runs (docs/10 §8, P4-10).

One ``Job`` per planned run: queued -> running -> succeeded/failed. ``update_job_state`` is the store's only
in-place update; evidence is only ever appended. A failing run marks its job failed and the runner continues.
"""

from collections.abc import Callable, Sequence

from reval.core.canonical import content_id
from reval.domain import Evidence
from reval.domain.plan import PlannedRun
from reval.store import Job, JobState, SqlStore


def _new_job_id(store: SqlStore, plan_id: str, candidate_id: str) -> str:
    """Deterministic id; re-executing the same plan gets a fresh attempt number instead of a clash."""
    attempt = 0
    while True:
        jid = content_id({"plan": plan_id, "run": candidate_id, "attempt": attempt})[:16]
        if store.get_job(jid) is None:
            return jid
        attempt += 1


def run_jobs(
    store: SqlStore,
    plan_id: str,
    runs: Sequence[PlannedRun],
    execute: Callable[[PlannedRun], tuple[Evidence, ...]],
) -> tuple[tuple[Evidence, ...], tuple[Job, ...]]:
    """Execute ``runs`` in order; returns the evidence produced and the final job records."""
    evidence: list[Evidence] = []
    jobs: list[Job] = []
    for run in runs:
        payload = {
            "plan_id": plan_id,
            "candidate_id": run.candidate_id,
            "producer_id": run.producer_id,
            "subject_id": run.subject_id,
            "cost": run.cost,
        }
        job = Job(
            id=_new_job_id(store, plan_id, run.candidate_id),
            kind="run_plan",
            state=JobState.QUEUED,
            payload=payload,
        )
        store.put_job(job)
        store.update_job_state(job.id, JobState.RUNNING)
        try:
            produced = execute(run)
        except Exception as exc:  # a failed producer must not stop the remaining runs
            failure = {"error": f"{type(exc).__name__}: {exc}"}
            store.update_job_state(job.id, JobState.FAILED, result=failure)
            jobs.append(job.model_copy(update={"state": JobState.FAILED, "result": failure}))
            continue
        success = {"evidence_ids": sorted(e.id for e in produced)}
        store.update_job_state(job.id, JobState.SUCCEEDED, result=success)
        evidence.extend(produced)
        jobs.append(job.model_copy(update={"state": JobState.SUCCEEDED, "result": success}))
    return tuple(evidence), tuple(jobs)
