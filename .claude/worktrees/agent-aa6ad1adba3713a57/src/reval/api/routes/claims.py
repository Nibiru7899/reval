from fastapi import APIRouter, Depends, HTTPException, Query

from reval.api.deps import assessed, get_project, require_default_project
from reval.api.schemas import Justification
from reval.domain import Assessment, Status
from reval.report.explain import explain_claim
from reval.services import Project

router = APIRouter(prefix="/projects/{p}", dependencies=[Depends(require_default_project)], tags=["claims"])


@router.get("/claims")
def list_claims(
    project: Project = Depends(get_project),  # noqa: B008
    snapshot: str | None = Query(None, description="Snapshot id; default: the latest assessed one."),
    status: Status | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Assessment]:
    """Latest assessment of every claim, sorted by claim id."""
    _, items = assessed(project, snapshot)
    rows = [items[k] for k in sorted(items) if status is None or items[k].status is status]
    return rows[offset : offset + limit]


@router.get("/claims/{c}/assessment")
def get_assessment(
    c: str,
    project: Project = Depends(get_project),  # noqa: B008
    snapshot: str | None = None,
) -> Assessment:
    """Latest assessment of one claim."""
    _, items = assessed(project, snapshot)
    if c not in items:
        raise HTTPException(status_code=404, detail=f"unknown claim {c!r}")
    return items[c]


@router.get("/claims/{c}/justification")
def get_justification(
    c: str,
    project: Project = Depends(get_project),  # noqa: B008
    snapshot: str | None = None,
) -> Justification:
    """Deterministic justification text (same renderer as ``reval explain``)."""
    snap, items = assessed(project, snapshot)
    if c not in items or c not in snap.claims:
        raise HTTPException(status_code=404, detail=f"unknown claim {c!r}")
    evidence = {e.id: e for e in project.store.list_evidence()}
    return Justification(claim_id=c, snapshot_id=snap.id, text=explain_claim(snap, items[c], evidence, c))
