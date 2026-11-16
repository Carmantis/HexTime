"""Alembic environment.

The database URL comes from the application settings, never from alembic.ini,
so ``alembic upgrade head`` always targets the same database the app itself
opens. Pass ``-x url=...`` to point a migration at a throwaway database, which
is what CI does when it checks the migrations against PostgreSQL.
"""

from logging.config import fileConfig
from typing import Any

from sqlalchemy import create_engine, pool

import app.core.db  # noqa: F401  (importing registers the SQLite foreign-key listener)
from alembic import context
from app.core.config import get_settings
from app.core.db import create_db_engine
from app.models import Base
from app.models.base import UtcDateTime

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: the app runs migrations at startup, and
    # fileConfig's default would switch off every logger that already exists,
    # uvicorn's and the app's own (failed emails, for one) included.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

#: Autogenerate compares the database against this. Every model must be
#: imported in app/models/__init__.py or its table silently goes missing.
target_metadata = Base.metadata


def _url_override() -> str | None:
    return context.get_x_argument(as_dictionary=True).get("url")


def _render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Render custom column types as plain SQLAlchemy types.

    A migration must never import application code. If it did, renaming or
    moving a type later would break every migration already written, and those
    are history that has to keep running. UtcDateTime emits no DDL of its own —
    the UTC normalising happens in Python — so at the database level it is
    exactly DateTime(timezone=True).

    Returning False means "use Alembic's default rendering".
    """
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure(**kwargs: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        render_item=_render_item,
        # SQLite cannot ALTER most things. Batch mode rebuilds the table
        # instead, which is what makes the same migration run on both the
        # desktop SQLite file and the server's PostgreSQL.
        render_as_batch=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    url = _url_override() or get_settings().resolved_database_url
    _configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run the migrations."""
    override = _url_override()
    if override:
        engine = create_engine(override, poolclass=pool.NullPool)
    else:
        # Goes through the app's own factory so the data directory is created.
        engine = create_db_engine(get_settings())

    with engine.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()

    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
