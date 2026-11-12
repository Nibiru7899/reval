"""Git and lock-file adapters (do I/O). Contract: docs/10 §9."""

from reval.gitio.git import read_file_at_rev, resolve_rev, snapshot_at_rev
from reval.gitio.lockfile import LOCK_FILE, parse_lock, read_lock, write_lock

__all__ = [
    "LOCK_FILE",
    "parse_lock",
    "read_file_at_rev",
    "read_lock",
    "resolve_rev",
    "snapshot_at_rev",
    "write_lock",
]
