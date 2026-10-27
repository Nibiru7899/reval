"""Execution context handed to producers; enforces declared dependencies (docs/10 §7, D11)."""

import json
from pathlib import Path
from typing import Any

import yaml

from reval.core.canonical import sha256_hex
from reval.domain.engineering import Assumption
from reval.domain.evidence import Producer
from reval.domain.selectors import Selector
from reval.domain.settings import DEFAULT_SETTINGS, ReValSettings
from reval.domain.snapshot import Snapshot
from reval.errors import MissingExtraError, ProducerError, UndeclaredDependencyError


def _pointer_get(doc: Any, pointer: str) -> Any:
    cur = doc
    for raw in pointer.split("/")[1:]:
        seg = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            if seg not in cur:
                raise ProducerError(f"pointer {pointer!r} not found (missing {seg!r})")
            cur = cur[seg]
        elif isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError):
                raise ProducerError(f"pointer {pointer!r} not found (bad index {seg!r})") from None
        else:
            raise ProducerError(f"pointer {pointer!r} descends into a scalar at {seg!r}")
    return cur


def _prefix_covers(dep_pointer: str, requested: str) -> bool:
    d, r = dep_pointer.split("/")[1:], requested.split("/")[1:]
    return len(d) <= len(r) and r[: len(d)] == d


class Context:
    """Gives a producer access to exactly what it declared in ``depends_on`` and ``assumes``."""

    def __init__(
        self,
        project_root: Path,
        snapshot: Snapshot,
        producer: Producer,
        settings: ReValSettings = DEFAULT_SETTINGS,
    ) -> None:
        self._root = Path(project_root)
        self._snapshot = snapshot
        self._producer = producer
        self._settings = settings
        self._deps = tuple(Selector.parse(s) for s in producer.depends_on)

    def _artifact_path(self, artifact_id: str) -> Path:
        art = self._snapshot.artifacts.get(artifact_id)
        if art is None:
            raise UndeclaredDependencyError(f"artifact {artifact_id!r} is not in the snapshot")
        return self._root / art.path

    def load(self, artifact_id: str) -> Any:
        """Load an artifact the producer declared. Column-only deps return just those columns plus the key."""
        deps = [d for d in self._deps if d.artifact_id == artifact_id]
        if not deps:
            raise UndeclaredDependencyError(
                f"{self._producer.id} loads {artifact_id!r} but does not declare it in depends_on"
            )
        if any(d.is_whole for d in deps):
            columns: tuple[str, ...] | None = None
        elif all(d.pointer is not None for d in deps):
            raise UndeclaredDependencyError(
                f"{self._producer.id} declares only pointer selectors on {artifact_id!r}; use ctx.param(...)"
            )
        else:
            declared = {c for d in deps for c in d.columns}
            key = self._snapshot.artifacts[artifact_id].key
            columns = tuple(sorted(declared | set(key)))
        return self._read(self._artifact_path(artifact_id), columns)

    @staticmethod
    def _read(path: Path, columns: tuple[str, ...] | None) -> Any:
        suffix = path.suffix.lower()
        if suffix in (".joblib", ".pkl"):
            try:
                import joblib  # type: ignore[import-untyped]
            except ImportError as exc:
                raise MissingExtraError("motor") from exc
            return joblib.load(path)
        if suffix in (".yaml", ".yml"):
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        if suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if suffix in (".parquet", ".csv"):
            try:
                import pandas as pd  # type: ignore[import-untyped]
            except ImportError as exc:
                raise MissingExtraError("motor") from exc
            if suffix == ".parquet":
                return pd.read_parquet(path, columns=None if columns is None else list(columns))
            return pd.read_csv(path, usecols=None if columns is None else list(columns))
        return path.read_bytes()

    def param(self, selector: str) -> Any:
        """Value at a pointer selector (``params#/a/b``) covered by a declared dependency."""
        sel = Selector.parse(selector)
        if sel.pointer is None:
            raise UndeclaredDependencyError(f"ctx.param needs a pointer selector, got {selector!r}")
        ok = any(
            d.artifact_id == sel.artifact_id
            and (d.is_whole or (d.pointer is not None and _prefix_covers(d.pointer, sel.pointer)))
            for d in self._deps
        )
        if not ok:
            raise UndeclaredDependencyError(
                f"{self._producer.id} did not declare a dependency covering {selector!r}"
            )
        doc = yaml.safe_load(self._artifact_path(sel.artifact_id).read_text(encoding="utf-8"))
        return _pointer_get(doc, sel.pointer)

    def assumption(self, assumption_id: str) -> Assumption:
        """An assumption the producer declared in ``assumes``."""
        if assumption_id not in self._producer.assumes:
            raise UndeclaredDependencyError(
                f"{self._producer.id} did not declare assumption {assumption_id!r}"
            )
        try:
            return self._snapshot.assumptions[assumption_id]
        except KeyError:
            raise UndeclaredDependencyError(f"assumption {assumption_id!r} is not in the snapshot") from None

    @property
    def seed(self) -> int:
        """Deterministic per (producer, snapshot)."""
        return int(sha256_hex((self._producer.id + self._snapshot.id).encode())[:8], 16)

    @property
    def settings(self) -> ReValSettings:
        return self._settings
