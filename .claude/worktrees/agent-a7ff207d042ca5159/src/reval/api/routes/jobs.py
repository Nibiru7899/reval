import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from reval.api.deps import AppState, get_state
from reval.store import Job, JobState

router = APIRouter(tags=["jobs"])

_TERMINAL = {JobState.SUCCEEDED, JobState.FAILED}
_POLL_SECONDS = 0.1


def _lookup(state: AppState, job_id: str) -> Job:
    # Deliberately lock-free: a running job holds the project lock, and polling must still work.
    job = state.project().store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id!r}")
    return job


def _event(name: str, job: Job) -> str:
    return f"event: {name}\ndata: {json.dumps(job.model_dump(mode='json'), sort_keys=True)}\n\n"


@router.get("/jobs/{job_id}")
def get_job(job_id: str, state: AppState = Depends(get_state)) -> Job:  # noqa: B008
    """Poll a job."""
    return _lookup(state, job_id)


@router.get(
    "/jobs/{job_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE: state, progress, done"}},
)
async def stream_job_events(job_id: str, state: AppState = Depends(get_state)) -> StreamingResponse:  # noqa: B008
    """Server-sent events: ``state`` on every change, ``progress`` once running, ``done`` at the end."""
    await asyncio.to_thread(_lookup, state, job_id)

    async def gen() -> AsyncIterator[str]:
        last: JobState | None = None
        while True:
            job = await asyncio.to_thread(_lookup, state, job_id)
            if job.state is not last:
                last = job.state
                yield _event("state", job)
                if job.state is JobState.RUNNING:
                    yield _event("progress", job)
            if job.state in _TERMINAL:
                yield _event("done", job)
                return
            await asyncio.sleep(_POLL_SECONDS)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
