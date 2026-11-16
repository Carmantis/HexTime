"""Migrations must produce exactly the schema the models describe.

Every other test builds its tables with ``Base.metadata.create_all``. That
means a model change with no matching migration would pass the whole suite and
only fail on a real deployment, where migrations are the only thing that runs.
These tests close that gap by running the real migrations.
"""

from argparse import Namespace
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text

from alembic import command
from app.models import Base

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_config(url: str) -> Config:
    """An Alembic config pointed at a throwaway database.

    The URL is passed the same way the command line does it (``-x url=...``),
    so the test exercises the real env.py rather than a special path.
    """
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.cmd_opts = Namespace(x=[f"url={url}"])
    return config


def _table_columns(engine: Engine) -> dict[str, list[str]]:
    """Table name -> sorted column names, ignoring Alembic's bookkeeping table."""
    inspector = inspect(engine)
    return {
        table: sorted(column["name"] for column in inspector.get_columns(table))
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


@pytest.fixture
def migrated_engine(tmp_path: Path) -> Engine:
    """A database built by running the migrations, not by create_all."""
    url = f"sqlite+pysqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(_alembic_config(url), "head")
    return create_engine(url)


def test_migrations_and_models_describe_the_same_schema(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    """The drift detector: fails when a model changed without a migration."""
    from_models = create_engine(f"sqlite+pysqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(from_models)

    assert _table_columns(migrated_engine) == _table_columns(from_models)

    from_models.dispose()
    migrated_engine.dispose()


def test_migration_creates_every_table(migrated_engine: Engine) -> None:
    expected = set(Base.metadata.tables)

    assert set(_table_columns(migrated_engine)) == expected
    assert len(expected) == 13

    migrated_engine.dispose()


def test_running_timer_index_keeps_its_where_clause(migrated_engine: Engine) -> None:
    """A partial index is easy to lose in autogenerate.

    Without the WHERE clause this becomes a plain unique index on user_id,
    which would allow a user only one time entry ever instead of only one
    *running* one.
    """
    with migrated_engine.connect() as connection:
        sql = connection.execute(
            text(
                "SELECT sql FROM sqlite_master WHERE type='index' "
                "AND name='uq_time_entries_one_running_per_user'"
            )
        ).scalar_one()

    assert "WHERE ended_at IS NULL" in sql

    migrated_engine.dispose()


def test_downgrade_removes_every_table(tmp_path: Path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'roundtrip.db'}"
    config = _alembic_config(url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(url)
    assert _table_columns(engine) == {}
    engine.dispose()


def test_team_admins_become_leads_and_admin_is_no_role_any_more(tmp_path: Path) -> None:
    """Teams have had leads and members only since 2026-10-08."""
    url = f"sqlite+pysqlite:///{tmp_path / 'roles.db'}"
    config = _alembic_config(url)
    command.upgrade(config, "e4b9d2f6a813")
    engine = create_engine(url)
    user, team = "11111111111111111111111111111111", "22222222222222222222222222222222"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, display_name, locale, theme, is_active, is_admin,"
                " created_at) VALUES (:id, 'Liisa', 'fi', 'dark', 1, 0, '2026-10-01')"
            ),
            {"id": user},
        )
        connection.execute(
            text(
                "INSERT INTO teams (id, name, created_by, created_at)"
                " VALUES (:t, 'Web', :u, '2026-10-01')"
            ),
            {"t": team, "u": user},
        )
        connection.execute(
            text(
                "INSERT INTO team_members (team_id, user_id, role, joined_at)"
                " VALUES (:t, :u, 'admin', '2026-10-01')"
            ),
            {"t": team, "u": user},
        )

    command.upgrade(config, "head")

    with engine.begin() as connection:
        assert connection.execute(text("SELECT role FROM team_members")).scalar_one() == "lead"
    with pytest.raises(Exception, match="CHECK constraint failed"), engine.begin() as connection:
        connection.execute(text("UPDATE team_members SET role = 'admin'"))
    engine.dispose()
