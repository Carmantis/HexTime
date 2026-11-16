"""Shared test fixtures.

Every Settings object here is built with ``_env_file=None`` so a developer's
local .env can never change what the tests assert.
"""

import os
from argparse import Namespace
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from alembic import command
from app.core.config import AppMode, Settings

# Importing this module also registers the SQLite foreign-key listener.
from app.core.csrf import CSRF_HEADER
from app.core.db import get_db
from app.core.email import Email, get_mailer
from app.main import create_app
from app.models import Base, Project, User

SERVER_SETTINGS: dict[str, Any] = {
    "app_mode": AppMode.SERVER,
    "allowed_email_domain": "example.org",
    "public_base_url": "https://hextime.example.fi",
    "secret_key": "test-secret-key",
    # Server mode has no sensible default database; it must be configured.
    "database_url": "postgresql+psycopg://hextime:secret@localhost:5432/hextime",
    # Tests never send mail: they swap in a recording mailer (see test_accounts).
    "smtp_host": "console",
}


def build_settings(**overrides: Any) -> Settings:
    """Build settings isolated from the environment.

    auto_migrate is off unless a test asks for it: a TestClient starts the
    app's lifespan, which would otherwise migrate the real database in the
    user's data directory.
    """
    return Settings(_env_file=None, **{"auto_migrate": False, **overrides})


def local_test_client(app: FastAPI, **kwargs: Any) -> TestClient:
    """A client that talks to a local-mode app the way the desktop UI does.

    Local mode answers only requests addressed to 127.0.0.1 or localhost and
    refuses changes without the CSRF header (app/core/csrf.py); the UI and
    HexStickyNote always send both. Tests of those checks build their own.
    """
    return TestClient(app, base_url="http://127.0.0.1", headers={CSRF_HEADER: "1"}, **kwargs)


def build_client(**overrides: Any) -> TestClient:
    """A client for an app with no compiled frontend mounted.

    Without serve_static=False these tests would pass or fail depending on
    whether `npm run build` had been run, because a mount on "/" changes how
    unmatched paths answer.
    """
    settings = build_settings(**overrides)
    app = create_app(settings=settings, serve_static=False)
    return TestClient(app) if settings.is_server else local_test_client(app)


@pytest.fixture
def local_client() -> TestClient:
    """Client for the single-user desktop mode."""
    return build_client(app_mode=AppMode.LOCAL)


@pytest.fixture
def server_client() -> TestClient:
    """Client for the multi-user server mode."""
    return build_client(**SERVER_SETTINGS)


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A fresh in-memory database with every table created.

    StaticPool keeps every connection pointing at the same in-memory database;
    without it each connection would get its own empty one.
    """
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session on the in-memory database."""
    with Session(engine) as session:
        yield session


@pytest.fixture
def user(db: Session) -> User:
    db_user = User(display_name="Test User")
    db.add(db_user)
    db.commit()
    return db_user


@pytest.fixture
def other_user(db: Session) -> User:
    db_user = User(display_name="Other User")
    db.add(db_user)
    db.commit()
    return db_user


@pytest.fixture
def api_client(db: Session) -> Iterator[TestClient]:
    """A client whose requests run against the in-memory database.

    get_db is overridden so no test can ever touch the real SQLite file in the
    user's data directory. The session is the same one the `db` fixture hands
    out, so a test can assert against the database directly after a request.
    """
    app = create_app(settings=build_settings(), serve_static=False)
    app.dependency_overrides[get_db] = lambda: db
    with local_test_client(app) as client:
        yield client


class Outbox(list[Email]):
    """A mailer that keeps what it was asked to send, for tests to read."""

    def send(self, email: Email) -> None:
        self.append(email)


@pytest.fixture
def outbox() -> Outbox:
    return Outbox()


@pytest.fixture
def server_settings() -> Settings:
    return build_settings(**SERVER_SETTINGS)


@pytest.fixture
def server(db: Session, outbox: Outbox, server_settings: Settings) -> Iterator[TestClient]:
    """A server-mode client on the in-memory database, sending mail to `outbox`.

    https:// because the session cookie is Secure: a client on plain http
    would, like a browser, never send it back.
    """
    app = create_app(settings=server_settings, serve_static=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_mailer] = lambda: outbox
    with TestClient(app, base_url="https://testserver") as client:
        yield client


@pytest.fixture
def project(db: Session, user: User) -> Project:
    """A billable project at 85,00 €/h, owned by `user`."""
    db_project = Project(
        name="Website",
        owner_user_id=user.id,
        billable_default=True,
        hourly_rate_cents=8500,
    )
    db.add(db_project)
    db.commit()
    return db_project


# ---------------------------------------------------------------------------
# PostgreSQL
#
# The desktop build runs on SQLite and the server build on PostgreSQL, and the
# two differ over exactly the features this application leans on. The tests
# that need a real PostgreSQL skip themselves unless TEST_DATABASE_URL is set;
# CI always sets it.
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent

POSTGRES_URL = os.environ.get("TEST_DATABASE_URL", "")

requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set TEST_DATABASE_URL to a PostgreSQL database to run these",
)


def alembic_config(url: str) -> Config:
    """Alembic aimed at one database, the way the command line does it."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.cmd_opts = Namespace(x=[f"url={url}"])
    return config


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    """An empty PostgreSQL database with the real migrations applied.

    The schema is dropped and rebuilt for every test, so one test's rows can
    never explain another test's result.
    """
    engine = create_engine(POSTGRES_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    command.upgrade(alembic_config(POSTGRES_URL), "head")

    yield engine
    engine.dispose()


@pytest.fixture
def pg(postgres_engine: Engine) -> Iterator[Session]:
    """A session on PostgreSQL."""
    with Session(postgres_engine) as session:
        yield session
