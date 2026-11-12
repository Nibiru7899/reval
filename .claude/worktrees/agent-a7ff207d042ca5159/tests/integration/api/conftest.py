"""API fixtures: a TestClient over a private copy of the mini project."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reval.api import ApiSettings, create_app
from reval.services import Project


@pytest.fixture
def client(root: Path) -> Iterator[TestClient]:
    with TestClient(create_app(ApiSettings(project_root=root))) as c:
        yield c


@pytest.fixture
def evidenced_root(root: Path) -> Path:
    """The mini project with evidence for every claim (the reval run --all state)."""
    Project.open(root).run_all()
    return root


@pytest.fixture
def evidenced_client(evidenced_root: Path) -> Iterator[TestClient]:
    with TestClient(create_app(ApiSettings(project_root=evidenced_root))) as c:
        yield c


@pytest.fixture
def stale_client(evidenced_root: Path) -> Iterator[TestClient]:
    """Evidence exists, then one measured temperature is edited: consumers of ``data`` go stale."""
    data = evidenced_root / "data" / "data.csv"
    data.write_text(data.read_text(encoding="utf-8").replace("g1,0.0,19.5", "g1,0.0,19.6"), encoding="utf-8")
    with TestClient(create_app(ApiSettings(project_root=evidenced_root))) as c:
        yield c
