"""Integration fixtures: a private, writable copy of the mini project."""

import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from reval.sdk import DEFAULT_REGISTRY

MINI_SRC = Path(__file__).resolve().parents[1] / "fixtures" / "mini_project"


def _drop_mini() -> None:
    for name in [m for m in sys.modules if m == "mini" or m.startswith("mini.")]:
        del sys.modules[name]


@pytest.fixture
def root(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "proj"
    shutil.copytree(MINI_SRC, root, ignore=shutil.ignore_patterns("__pycache__"))
    _drop_mini()
    DEFAULT_REGISTRY.clear()
    yield root
    _drop_mini()
    sys.path[:] = [p for p in sys.path if p != str(root.resolve())]
    DEFAULT_REGISTRY.clear()
