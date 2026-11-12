"""Shared fixture: a private copy of the mini project with producers loaded and a snapshot built."""

import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from reval.domain.snapshot import Snapshot
from reval.manifest import load_manifest
from reval.manifest.snapshot_builder import build_snapshot
from reval.sdk import DEFAULT_REGISTRY, ProducerRegistry

MINI_SRC = Path(__file__).resolve().parents[1] / "fixtures" / "mini_project"


@dataclass
class MiniProject:
    root: Path
    registry: ProducerRegistry

    def snapshot(self, git_rev: str | None = None) -> Snapshot:
        manifest = load_manifest(self.root / "reval.yaml")
        return build_snapshot(self.root, manifest, self.registry, git_rev=git_rev)


@pytest.fixture
def mini(tmp_path: Path) -> Iterator[MiniProject]:
    root = tmp_path / "proj"
    shutil.copytree(MINI_SRC, root, ignore=shutil.ignore_patterns("__pycache__"))
    for name in [m for m in sys.modules if m == "mini" or m.startswith("mini.")]:
        del sys.modules[name]
    DEFAULT_REGISTRY._items.clear()
    manifest = load_manifest(root / "reval.yaml")
    DEFAULT_REGISTRY.load_modules(list(manifest.producers), root)
    yield MiniProject(root, DEFAULT_REGISTRY)
    for name in [m for m in sys.modules if m == "mini" or m.startswith("mini.")]:
        del sys.modules[name]
    sys.path[:] = [p for p in sys.path if p != str(root.resolve())]
    DEFAULT_REGISTRY._items.clear()
