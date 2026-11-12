"""Request dependencies: the single project (D27), serialised access, and lookup helpers."""

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Depends, HTTPException, Request

from reval.api.settings import PROJECT_ID, ApiSettings
from reval.domain import Assessment, Snapshot
from reval.errors import RevalError
from reval.gitio import snapshot_at_rev
from reval.gitio.git import repo_subdir
from reval.services import Project


@dataclass
class AppState:
    """Process-wide state. ``lock`` is a plain Lock on purpose: FastAPI may release a generator
    dependency on another worker thread than the one that acquired it, which an RLock forbids."""

    settings: ApiSettings
    lock: threading.Lock = field(default_factory=threading.Lock)
    _open_lock: threading.Lock = field(default_factory=threading.Lock)
    _project: Project | None = None

    def project(self) -> Project:
        # Project.open resets the global producer registry, so it must happen once per process.
        with self._open_lock:
            if self._project is None:
                self._project = Project.open(self.settings.project_root)
            return self._project


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.reval
    return state


def require_default_project(p: str) -> None:
    if p != PROJECT_ID:
        raise HTTPException(status_code=404, detail=f"unknown project {p!r}; only {PROJECT_ID!r} exists")


def get_project(state: AppState = Depends(get_state)) -> Iterator[Project]:  # noqa: B008
    """The project, held exclusively for the duration of the request (producers share global state)."""
    with state.lock:
        yield state.project()


def resolve_snapshot(project: Project, ref: str) -> Snapshot:
    """A stored snapshot by id or unique id prefix, else the lock committed at git revision ``ref``."""
    stored = [
        s for s in project.store.list_snapshots() if s.id == ref or (len(ref) >= 6 and s.id.startswith(ref))
    ]
    exact = [s for s in stored if s.id == ref]
    if exact:
        return exact[0]
    if len(stored) == 1:
        return stored[0]
    if len(stored) > 1:
        raise HTTPException(status_code=400, detail=f"snapshot prefix {ref!r} is ambiguous")
    try:
        repo_root, subdir = repo_subdir(Path(project.root))
        return snapshot_at_rev(repo_root, ref, subdir)
    except RevalError:
        raise HTTPException(status_code=404, detail=f"unknown snapshot {ref!r}") from None


def assessed(project: Project, ref: str | None) -> tuple[Snapshot, dict[str, Assessment]]:
    """Stored assessments for ``ref`` (default: the most recently assessed snapshot).

    Nothing stored yet means the snapshot is assessed once; reads do not append a batch otherwise.
    """
    if ref is None:
        sid = project.store.latest_assessed_snapshot()
        if sid is None:
            snap = project.snapshot()
            return snap, project.assess(snap)
        found = project.store.get_snapshot(sid)
        if found is None:  # an assessment batch without its snapshot row cannot happen; fail closed
            raise HTTPException(status_code=500, detail=f"snapshot {sid} missing from the store")
        return found, project.store.get_assessments(sid)
    snap = resolve_snapshot(project, ref)
    stored = project.store.get_assessments(snap.id)
    return snap, stored if stored else project.assess(snap)
