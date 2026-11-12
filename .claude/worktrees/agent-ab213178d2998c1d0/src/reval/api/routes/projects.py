from fastapi import APIRouter, Depends

from reval.api.deps import get_project
from reval.api.schemas import ProjectInfo
from reval.api.settings import PROJECT_ID
from reval.services import Project

router = APIRouter(tags=["projects"])


@router.get("/projects")
def list_projects(project: Project = Depends(get_project)) -> list[ProjectInfo]:  # noqa: B008
    """Exactly one project exists (D27)."""
    snap = project.snapshot()
    return [ProjectInfo(id=PROJECT_ID, name=project.manifest.project, claims=len(snap.claims))]
