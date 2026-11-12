"""Shared helpers: a throwaway copy of the mini project opened as a Project."""

import shutil
from pathlib import Path

from reval.services.project import Project

MINI = Path(__file__).resolve().parents[1] / "fixtures" / "mini_project"


def copy_mini(tmp_path: Path, name: str = "mini") -> Path:
    root = tmp_path / name
    shutil.copytree(MINI, root, ignore=shutil.ignore_patterns("__pycache__", ".reval"))
    return root


def edit(root: Path, rel: str, old: str, new: str) -> None:
    p = root / rel
    data = p.read_bytes()  # bytes: text mode would rewrite line endings on Windows
    assert old.encode() in data
    p.write_bytes(data.replace(old.encode(), new.encode()))


def open_project(root: Path) -> Project:
    return Project.open(root)
