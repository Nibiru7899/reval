"""Alembic helpers behind ``reval db upgrade`` (adapter layer; does I/O). Needs the ``server`` extra."""

from pathlib import Path
from typing import Any

from reval.errors import MissingExtraError

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(url: str) -> Any:
    """An Alembic ``Config`` pointing at the packaged migrations and ``url``."""
    try:
        from alembic.config import Config
    except ImportError as exc:
        raise MissingExtraError("server") from exc
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.attributes["url"] = url
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    """Apply migrations up to ``revision`` on the database at ``url``."""
    try:
        from alembic import command
    except ImportError as exc:
        raise MissingExtraError("server") from exc
    command.upgrade(alembic_config(url), revision)
