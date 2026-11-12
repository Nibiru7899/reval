"""Helpers for diff/freshness tests on the mini project: run producers, edit files, rebuild domain objects."""

from typing import Any

from reval.domain.evidence import Evidence
from reval.domain.snapshot import Snapshot
from reval.sdk.runner import run_producer


def pid(mini: Any, name: str) -> str:
    """Full producer id of the mini producer whose function is ``name``."""
    (match,) = [rp.meta.id for rp in mini.registry.all() if rp.meta.id.endswith(f":{name}")]
    return str(match)


def run(mini: Any, snap: Snapshot, name: str, subject_id: str) -> Evidence:
    """Run one mini producer on one subject; it yields exactly one evidence item."""
    (e,) = run_producer(mini.registry, pid(mini, name), snap.subjects[subject_id], snap, mini.root)
    return e


def edit(mini: Any, relpath: str, old: str, new: str) -> None:
    """Replace exactly one occurrence of ``old`` with ``new`` in a project file."""
    path = mini.root / relpath
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} must occur once in {relpath}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def append(mini: Any, relpath: str, text: str) -> None:
    path = mini.root / relpath
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def resnap(snap: Snapshot, **updates: Any) -> Snapshot:
    """A copy of ``snap`` with some fields replaced and the id recomputed."""
    fields = {k: getattr(snap, k) for k in type(snap).model_fields if k != "id"}
    fields.update(updates)
    return Snapshot.create(**fields)


def reev(e: Evidence, **updates: Any) -> Evidence:
    """A copy of ``e`` with some fields replaced and the id recomputed."""
    fields = {k: getattr(e, k) for k in type(e).model_fields if k != "id"}
    fields.update(updates)
    return Evidence.create(**fields)


def run_all(mini: Any, snap: Snapshot) -> dict[tuple[str, str], Evidence]:
    """Every available (producer function name, subject id) -> evidence at ``snap``."""
    out: dict[tuple[str, str], Evidence] = {}
    for rp in mini.registry.all():
        name = rp.meta.id.rsplit(":", 1)[1]
        for sid in sorted(snap.subjects):
            sub = snap.subjects[sid]
            if rp.available_for is None or rp.available_for(sub):
                (e,) = run_producer(mini.registry, rp.meta.id, sub, snap, mini.root)
                out[(name, sid)] = e
    return out
