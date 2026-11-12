from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from reval.api.deps import get_project, require_default_project, resolve_snapshot
from reval.api.schemas import SnapshotRef
from reval.report import Report, build_report
from reval.report.render import render_html, render_markdown
from reval.services import Project

router = APIRouter(prefix="/projects/{p}", dependencies=[Depends(require_default_project)], tags=["reports"])


@router.post("/reports", status_code=201)
def create_report(body: SnapshotRef, project: Project = Depends(get_project)) -> Report:  # noqa: B008
    """Assess the snapshot (default: the working tree), build the report and store it."""
    snap = resolve_snapshot(project, body.snapshot) if body.snapshot is not None else None
    return build_report(project, snapshot=snap)


@router.get(
    "/reports/{report_id}",
    response_model=None,
    responses={
        200: {
            "model": Report,
            "content": {"text/html": {}, "text/markdown": {}},
            "description": "format=json (default) returns the Report; html and md return rendered text.",
        }
    },
)
def get_report(
    report_id: str,
    format: Literal["json", "html", "md"] = Query("json"),
    project: Project = Depends(get_project),  # noqa: B008
) -> Response:
    """A stored report as canonical JSON, self-contained HTML or Markdown."""
    body = project.store.get_report(report_id)
    if body is None:
        raise HTTPException(status_code=404, detail=f"unknown report {report_id!r}")
    report = Report.model_validate(body)
    if format == "html":
        return HTMLResponse(render_html(report))
    if format == "md":
        return PlainTextResponse(render_markdown(report), media_type="text/markdown; charset=utf-8")
    return Response(report.model_dump_json(), media_type="application/json")
