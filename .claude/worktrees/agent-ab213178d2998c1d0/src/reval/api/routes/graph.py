from fastapi import APIRouter, Depends, HTTPException

from reval.api.deps import get_project, require_default_project, resolve_snapshot
from reval.api.schemas import GraphEdge, GraphNode, GraphResponse
from reval.core.graph import EvidenceGraph
from reval.services import Project

router = APIRouter(prefix="/projects/{p}", dependencies=[Depends(require_default_project)], tags=["graph"])


@router.get("/graph")
def get_graph(
    project: Project = Depends(get_project),  # noqa: B008
    snapshot: str | None = None,
    focus: str | None = None,
) -> GraphResponse:
    """Evidence graph; ``focus`` (a node id such as ``claim:<id>``) keeps its cone and what it influences."""
    snap = resolve_snapshot(project, snapshot) if snapshot is not None else project.snapshot()
    stored = project.store.get_assessments(snap.id)
    g = EvidenceGraph.build(snap, project.store.list_evidence())
    try:
        body = g.to_json(focus)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown graph node {focus!r}") from None
    nodes = []
    for n in body["nodes"]:
        status = None
        if n["type"] == "claim":
            a = stored.get(n["id"].removeprefix("claim:"))
            status = a.status if a is not None else None
        nodes.append(GraphNode(id=n["id"], type=n["type"], label=n["label"], status=status))
    return GraphResponse(
        snapshot_id=snap.id,
        nodes=tuple(nodes),
        edges=tuple(GraphEdge(**e) for e in body["edges"]),
    )
