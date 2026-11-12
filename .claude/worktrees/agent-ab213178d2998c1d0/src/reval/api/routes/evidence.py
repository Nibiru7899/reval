from fastapi import APIRouter, Depends, HTTPException

from reval.api.deps import get_project, require_default_project
from reval.domain import Evidence
from reval.services import Project

router = APIRouter(prefix="/projects/{p}", dependencies=[Depends(require_default_project)], tags=["evidence"])


@router.get("/evidence/{e}")
def get_evidence(e: str, project: Project = Depends(get_project)) -> Evidence:  # noqa: B008
    """One evidence record by id."""
    for item in project.store.list_evidence():
        if item.id == e:
            return item
    raise HTTPException(status_code=404, detail=f"unknown evidence {e!r}")
