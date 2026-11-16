"""Starting the app migrates its own database, after taking a copy."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.startup import (
    KEEP_BACKUPS,
    DatabaseTooNewError,
    _alembic_config,
    back_up,
    prepare_local_database,
    prune_backups,
    sqlite_file_of,
)
from tests.conftest import build_settings


def settings_for(db: Path):
    return build_settings(database_url=f"sqlite+pysqlite:///{db}")


def table_names(db: Path) -> list[str]:
    engine = create_engine(f"sqlite+pysqlite:///{db}")
    names = inspect(engine).get_table_names()
    engine.dispose()
    return names


def test_starting_creates_the_whole_schema(tmp_path: Path) -> None:
    db = tmp_path / "hextime.db"

    prepare_local_database(settings_for(db))

    names = table_names(db)
    assert "time_entries" in names
    assert "projects" in names
    assert "alembic_version" in names


def test_first_start_has_nothing_to_back_up(tmp_path: Path) -> None:
    db = tmp_path / "hextime.db"

    backup = prepare_local_database(settings_for(db))

    assert backup is None
    assert list(tmp_path.glob("*.bak")) == []


def test_a_start_with_a_pending_migration_backs_up_first(tmp_path: Path) -> None:
    """The safety net: an unattended migration must never be the only copy."""
    db = tmp_path / "hextime.db"
    url = f"sqlite+pysqlite:///{db}"
    prepare_local_database(settings_for(db))
    # Step back one revision, as if the app had just been updated.
    command.downgrade(_alembic_config(url), "-1")

    backup = prepare_local_database(settings_for(db))

    assert backup is not None
    assert backup.is_file()
    assert backup.suffix == ".bak"


def test_a_start_with_nothing_to_migrate_takes_no_copy(tmp_path: Path) -> None:
    """Copying on every launch would fill the data directory for nothing."""
    db = tmp_path / "hextime.db"
    prepare_local_database(settings_for(db))

    backup = prepare_local_database(settings_for(db))

    assert backup is None
    assert list(tmp_path.glob("*.bak")) == []


def test_only_the_newest_backups_are_kept(tmp_path: Path) -> None:
    db = tmp_path / "hextime.db"
    names = [f"hextime-2026100{day}T120000Z.bak" for day in range(1, 8)]
    for name in names:
        (tmp_path / name).write_text("copy")
    (tmp_path / "unrelated.bak").write_text("not ours")

    deleted = prune_backups(db)

    kept = sorted(path.name for path in tmp_path.glob("hextime-*.bak"))
    assert kept == names[-KEEP_BACKUPS:]
    assert [path.name for path in deleted] == names[:2]
    assert (tmp_path / "unrelated.bak").is_file()


def test_running_twice_is_harmless(tmp_path: Path) -> None:
    db = tmp_path / "hextime.db"

    prepare_local_database(settings_for(db))
    prepare_local_database(settings_for(db))

    assert "time_entries" in table_names(db)


def test_the_missing_data_directory_is_created(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "deeper" / "hextime.db"

    prepare_local_database(settings_for(db))

    assert db.is_file()


def test_backing_up_a_file_that_is_not_there_yet(tmp_path: Path) -> None:
    assert back_up(tmp_path / "nothing.db") is None


def test_only_sqlite_databases_are_backed_up() -> None:
    """PostgreSQL is backed up by pg_dump on the server, not by the app."""
    assert sqlite_file_of("postgresql+psycopg://u:p@localhost/hextime") is None
    assert sqlite_file_of("sqlite+pysqlite:///:memory:") is None
    assert sqlite_file_of("sqlite+pysqlite:///data/hextime.db") == Path("data/hextime.db")


def test_starting_also_clears_an_old_pile_of_copies(tmp_path: Path) -> None:
    """Older versions copied on every launch; a normal start tidies that up."""
    db = tmp_path / "hextime.db"
    prepare_local_database(settings_for(db))
    for day in range(1, 10):
        (tmp_path / f"hextime-2026100{day}T120000Z.bak").write_text("copy")

    prepare_local_database(settings_for(db))

    assert len(list(tmp_path.glob("hextime-*.bak"))) == KEEP_BACKUPS


def test_migrating_at_startup_keeps_the_apps_loggers_on(tmp_path: Path) -> None:
    """Alembic configures logging from alembic.ini. It must not silence the
    loggers that already exist, or a failed email would never be logged."""
    import logging

    email_log = logging.getLogger("hextime.email")
    email_log.disabled = False

    prepare_local_database(settings_for(tmp_path / "hextime.db"))

    assert not email_log.disabled
    assert not logging.getLogger("uvicorn.error").disabled


def _written_by_a_newer_version(db: Path) -> None:
    """A database migrated to a revision this version has never heard of."""
    prepare_local_database(settings_for(db))
    engine = create_engine(f"sqlite+pysqlite:///{db}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'f00dfacecafe'"))
    engine.dispose()


def test_a_database_from_a_newer_version_is_refused_untouched(tmp_path: Path) -> None:
    db = tmp_path / "hextime.db"
    _written_by_a_newer_version(db)
    before = db.read_bytes()

    with pytest.raises(DatabaseTooNewError, match="f00dfacecafe"):
        prepare_local_database(settings_for(db))

    assert db.read_bytes() == before
    # No copy either: nothing was about to change.
    assert list(tmp_path.glob("*.bak")) == []
