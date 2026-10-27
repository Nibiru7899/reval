"""Producer registry and code hashing (docs/10 §7, D16)."""

import importlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from reval.core.canonical import sha256_hex
from reval.domain.engineering import Subject
from reval.domain.evidence import Producer

# Placeholder until load_modules recomputes it; nothing may read it before then.
PLACEHOLDER_CODE_HASH = "unloaded"


class RegisteredProducer(NamedTuple):
    meta: Producer
    fn: Callable[..., Any]
    available_for: Callable[[Subject], bool] | None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def code_hash(fn: Callable[..., Any], project_root: Path) -> str:
    """Hash of the producer's whole top-level package (so helper edits count) plus its qualname."""
    module = sys.modules.get(fn.__module__)
    mod_file = getattr(module, "__file__", None)
    if module is None or mod_file is None:
        raise ValueError(f"cannot locate source of {fn.__module__!r}")
    top = sys.modules.get(fn.__module__.split(".")[0])
    top_paths = list(getattr(top, "__path__", []) or [])
    files: list[Path]
    if top_paths and _is_within(Path(top_paths[0]), project_root):
        pkg_dir = Path(top_paths[0]).resolve()
        files = sorted(pkg_dir.rglob("*.py"), key=lambda p: p.relative_to(project_root.resolve()).as_posix())
    else:
        files = [Path(mod_file)]
    root = project_root.resolve()
    chunks: list[bytes] = []
    for f in files:
        rel = f.resolve().relative_to(root).as_posix() if _is_within(f, root) else f.name
        chunks.append(rel.encode() + b"\0" + f.read_bytes() + b"\0")
    return sha256_hex(b"".join(chunks) + fn.__qualname__.encode())


class ProducerRegistry:
    """Holds registered producers keyed by id."""

    def __init__(self) -> None:
        self._items: dict[str, RegisteredProducer] = {}

    def register(self, rp: RegisteredProducer) -> None:
        if rp.meta.id in self._items:
            raise ValueError(f"duplicate producer id {rp.meta.id!r}")
        self._items[rp.meta.id] = rp

    def get(self, producer_id: str) -> RegisteredProducer:
        try:
            return self._items[producer_id]
        except KeyError:
            raise KeyError(f"unknown producer {producer_id!r}") from None

    def all(self) -> tuple[RegisteredProducer, ...]:
        return tuple(self._items[k] for k in sorted(self._items))

    def load_modules(self, modules: Sequence[str], project_root: Path) -> None:
        """Import producer modules (project root on sys.path), then recompute every ``code_hash``."""
        root = str(Path(project_root).resolve())
        if root not in sys.path:
            sys.path.insert(0, root)
        for name in modules:
            importlib.import_module(name)
        for pid, rp in list(self._items.items()):
            meta = rp.meta.model_copy(update={"code_hash": code_hash(rp.fn, Path(project_root))})
            self._items[pid] = rp._replace(meta=meta)


DEFAULT_REGISTRY = ProducerRegistry()
