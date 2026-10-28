"""Git and lock-file adapters (do I/O). Contract: docs/10 §9."""

from reval.gitio.lockfile import LOCK_FILE, parse_lock, read_lock, write_lock

__all__ = ["LOCK_FILE", "parse_lock", "read_lock", "write_lock"]
