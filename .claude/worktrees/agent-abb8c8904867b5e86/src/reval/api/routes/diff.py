from fastapi import APIRouter, Depends, Query

from reval.api.deps import get_project, require_default_project, resolve_snapshot
from reval.api.schemas import DiffResponse, FreshnessEntry
from reval.services import Project

router = APIRouter(prefix="/projects/{p}", dependencies=[Depends(require_default_project)], tags=["diff"])


@router.get("/diff")
def get_diff(
    from_: str = Query(alias="from", description="Snapshot id, id prefix or git revision."),
    to: str | None = Query(None, description="Same forms; default: the working tree."),
    project: Project = Depends(get_project),  # noqa: B008
) -> DiffResponse:
    """Change set, evidence freshness and claim statuses between two snapshots."""
    a = resolve_snapshot(project, from_)
    b = resolve_snapshot(project, to) if to is not None else project.snapshot()
    rep = project.diff(a, b)
    return DiffResponse(
        from_snapshot=a.id,
        to_snapshot=b.id,
        changes=rep.changes,
        freshness={
            eid: FreshnessEntry(cls=fr.cls, inflation=fr.inflation, reasons=fr.reasons)
            for eid, fr in sorted(rep.freshness.items())
        },
        before=rep.before,
        after=rep.after,
        affected_claims=rep.affected_claims,
    )
