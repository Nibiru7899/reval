"""P6-05: Alembic upgrade on a fresh database, no drift, idempotent over create_all databases."""

import os
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from typer.testing import CliRunner

from reval.cli.main import app
from reval.domain import Snapshot
from reval.store import SqlStore
from reval.store.migrate import alembic_config, upgrade
from reval.store.tables import metadata

runner = CliRunner()


def _url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"


def test_upgrade_fresh_db_has_no_drift(tmp_path: Path) -> None:
    url = _url(tmp_path)
    upgrade(url)
    engine = create_engine(url)
    assert set(inspect(engine).get_table_names()) == set(metadata.tables) | {"alembic_version"}
    assert "seq" in {c["name"] for c in inspect(engine).get_columns("assessments")}
    engine.dispose()
    command.check(alembic_config(url))  # raises on drift between the migrations and tables.py


def test_upgrade_is_repeatable_and_downgrades(tmp_path: Path) -> None:
    url = _url(tmp_path)
    upgrade(url)
    upgrade(url)
    command.downgrade(alembic_config(url), "base")
    engine = create_engine(url)
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()


def test_upgrade_over_create_all_database(tmp_path: Path) -> None:
    url = _url(tmp_path)
    SqlStore(url).close()  # the SQLite dev path: create_all
    upgrade(url)
    command.check(alembic_config(url))


def test_cli_db_upgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVAL_DATABASE_URL", _url(tmp_path))
    r = runner.invoke(app, ["db", "upgrade", "--project", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "fresh.db").exists()


def test_cli_db_upgrade_default_url_is_project_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REVAL_DATABASE_URL", raising=False)
    r = runner.invoke(app, ["db", "upgrade", "--project", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".reval" / "reval.db").exists()


@pytest.mark.skipif(not os.environ.get("REVAL_TEST_POSTGRES_URL"), reason="needs REVAL_TEST_POSTGRES_URL")
def test_postgres_upgrade_and_roundtrip() -> None:
    """Runs in the CI `postgres` job only."""
    url = os.environ["REVAL_TEST_POSTGRES_URL"]
    upgrade(url)
    command.check(alembic_config(url))
    store = SqlStore(url)
    assert store.list_snapshots() == () or all(isinstance(s, Snapshot) for s in store.list_snapshots())
    store.close()
