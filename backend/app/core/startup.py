"""Work done once, when the application starts.

The desktop user never opens a terminal, so the application has to migrate its
own database. It takes a copy first: an unattended schema migration running on
someone's only record of their working hours is not a risk worth taking.

The copy is taken only when a migration is actually about to run, and only the
newest few are kept. Copying on every start would fill the data directory with
identical files, one per launch, for as long as the app is installed.
"""

import shutil
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import Settings

#: backend/, i.e. the directory holding alembic.ini and alembic/.
BACKEND_DIR = Path(__file__).resolve().parents[2]

#: How many pre-migration copies to keep. Each one is from before a different
#: schema change, so a few cover any upgrade a user is likely to want to undo.
KEEP_BACKUPS = 5


def sqlite_file_of(url: str) -> Path | None:
    """The file a SQLite URL points at, or None for other databases."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return None
    if not parsed.database or parsed.database == ":memory:":
        return None
    return Path(parsed.database)


def back_up(path: Path) -> Path | None:
    """Copy a database file beside itself. Returns None if there is nothing yet."""
    if not path.is_file():
        return None

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.stem}-{stamp}.bak")
    shutil.copy2(path, backup)
    return backup


def prune_backups(path: Path, keep: int = KEEP_BACKUPS) -> list[Path]:
    """Delete all but the newest `keep` copies of `path`. Returns the deleted.

    The names carry a UTC timestamp in a sortable form, so sorting by name
    is sorting by age and no file times have to be trusted.
    """
    backups = sorted(path.parent.glob(f"{path.stem}-*.bak"))
    stale = backups[:-keep] if keep > 0 else backups
    for backup in stale:
        backup.unlink()
    return stale


def _alembic_config(url: str) -> Config:
    """Alembic configuration aimed at one database.

    The URL is handed over the same way the command line does it (``-x url``),
    so this goes through the same env.py as a manual migration.
    """
    ini = BACKEND_DIR / "alembic.ini"
    if not ini.is_file():
        raise FileNotFoundError(f"alembic.ini not found at {ini}")

    config = Config(str(ini))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.cmd_opts = Namespace(x=[f"url={url}"])
    return config


def needs_migration(config: Config, url: str) -> bool:
    """True when the database is not at the newest schema revision."""
    heads = set(ScriptDirectory.from_config(config).get_heads())
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()
    return current != heads


class DatabaseTooNewError(RuntimeError):
    """The database was last opened by a newer HexTime than this one.

    Its schema revision is one this version has never heard of. Migrating
    would fail halfway, and running on it could misread what newer versions
    wrote, so the app refuses to start and leaves the file untouched.
    """


def check_not_newer(config: Config, url: str) -> None:
    """Raise DatabaseTooNewError if the database is at an unknown revision.

    An older revision is fine (that is what migrating is for); one this
    version does not know can only come from a newer version.
    """
    known = {revision.revision for revision in ScriptDirectory.from_config(config).walk_revisions()}
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
    finally:
        engine.dispose()
    unknown = current - known
    if unknown:
        raise DatabaseTooNewError(
            f"the database is at revision {', '.join(sorted(unknown))}, "
            "which this version of HexTime does not know: a newer version wrote it"
        )


def prepare_local_database(settings: Settings) -> Path | None:
    """Bring the database up to date, backing up a SQLite file first.

    Returns the backup that was taken, or None when none was needed: on the
    first start (nothing to copy yet), when the schema is already current, or
    when the database is not SQLite.
    """
    url = settings.resolved_database_url
    config = _alembic_config(url)

    backup: Path | None = None
    sqlite_file = sqlite_file_of(url)
    if sqlite_file is not None:
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)
        if sqlite_file.is_file():
            # Before the copy and the migration: nothing is touched.
            check_not_newer(config, url)
        if sqlite_file.is_file() and needs_migration(config, url):
            backup = back_up(sqlite_file)
        # Every start, not only after a copy: it also clears the pile older
        # versions left behind by copying on every launch.
        prune_backups(sqlite_file)

    command.upgrade(config, "head")
    return backup
