"""Alembic environment. URL: config.attributes["url"], then `-x url=`, then REVAL_DATABASE_URL."""

import os

from alembic import context
from sqlalchemy import create_engine

from reval.store.tables import metadata

config = context.config


def _url() -> str:
    url = config.attributes.get("url") or context.get_x_argument(as_dictionary=True).get("url")
    url = url or os.environ.get("REVAL_DATABASE_URL") or "sqlite:///.reval/reval.db"
    return str(url)


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata)
            with context.begin_transaction():
                context.run_migrations()
            connection.commit()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
