from fastapi import APIRouter, Depends, Query

from reval.api.deps import get_project, require_default_project
from reval.api.schemas import SnapshotSummary
from reval.domain import Snapshot
from reval.services import Project

router = APIRouter(
    prefix="/projects/{p}", dependencies=[Depends(require_default_project)], tags=["snapshots"]
)


@router.get("/snapshots")
def list_snapshots(
    project: Project = Depends(get_project),  # noqa: B008
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[SnapshotSummary]:
    """Stored snapshots, newest first."""
    snaps = list(reversed(project.store.list_snapshots()))[offset : offset + limit]
    return [SnapshotSummary(id=s.id, git_rev=s.git_rev, claims=len(s.claims)) for s in snaps]


@router.post("/snapshots", status_code=201)
def create_snapshot(project: Project = Depends(get_project)) -> Snapshot:  # noqa: B008
    """Snapshot the working tree and store it (idempotent on the snapshot id)."""
    return project.snapshot()
