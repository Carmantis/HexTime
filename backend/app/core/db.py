"""Database engine and sessions.

One place builds the engine; everything else receives a ``Session`` through
``Depends(get_db)``. Services take that session as an argument, which is what
makes them testable without HTTP.
"""

import sqlite3
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    """Turn on foreign key enforcement, which SQLite disables by default.

    Without this every ON DELETE rule is decorative on the desktop build while
    working correctly on PostgreSQL — exactly the kind of difference that only
    surfaces once real data is at stake.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_db_engine(settings: Settings) -> Engine:
    """Build an engine for these settings, creating the data directory if needed."""
    url = settings.resolved_database_url
    kwargs: dict[str, Any] = {}

    if url.startswith("sqlite"):
        # The desktop build answers HTTP from a background thread.
        kwargs["connect_args"] = {"check_same_thread": False}
        if not settings.database_url:
            settings.local_database_path.parent.mkdir(parents=True, exist_ok=True)

    return create_engine(url, **kwargs)


@lru_cache
def get_engine() -> Engine:
    """The process-wide engine, built once on first use."""
    return create_db_engine(get_settings())


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed again."""
    with get_session_factory()() as session:
        yield session
