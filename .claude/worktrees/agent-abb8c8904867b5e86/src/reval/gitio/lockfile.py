"""``reval.lock.json``: the committed, deterministic serialization of a Snapshot (ADR 0005, docs/10 §9)."""

import json
from pathlib import Path

from pydantic import ValidationError

from reval.domain.snapshot import Snapshot
from reval.errors import LockNotFoundError, StoreError

LOCK_FILE = "reval.lock.json"


def lock_text(snapshot: Snapshot) -> str:
    """Canonical lock text: sorted keys, 2-space indent, no timestamps, ``git_rev`` forced to null."""
    data = snapshot.model_copy(update={"git_rev": None}).model_dump(mode="json")
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_lock(project_root: Path, snapshot: Snapshot) -> Path:
    """Write ``reval.lock.json`` under ``project_root`` with LF newlines; returns its path."""
    path = Path(project_root) / LOCK_FILE
    # write_bytes, not write_text: on Windows text mode would turn "\n" into "\r\n" and break byte-identity.
    path.write_bytes(lock_text(snapshot).encode("utf-8"))
    return path


def parse_lock(data: bytes, source: str) -> Snapshot:
    """Parse lock bytes and verify the stored id equals the recomputed content id (D1).

    Raises StoreError for malformed JSON, a schema mismatch, or a hand-edited lock whose id no longer matches.
    """
    try:
        raw = json.loads(data.decode("utf-8"))
        return Snapshot.model_validate(raw)  # the model's validator recomputes the id
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoreError(f"{source}: not a valid lock file: {exc}") from exc
    except ValidationError as exc:
        raise StoreError(f"{source}: corrupted or hand-edited lock (id/schema check failed)") from exc


def read_lock(path: Path) -> Snapshot:
    """Read a lock file; a missing file raises LockNotFoundError."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except FileNotFoundError as exc:
        raise LockNotFoundError(f"no lock file at {p}") from exc
    except OSError as exc:
        raise StoreError(f"cannot read {p}: {exc}") from exc
    return parse_lock(data, str(p))
