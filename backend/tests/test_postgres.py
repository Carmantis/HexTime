"""The same rules, on PostgreSQL.

Every other test runs on SQLite, which is what the desktop build uses. The
server build uses PostgreSQL, and the two disagree about precisely the things
this application leans on: partial unique indexes, CHECK constraints, an enum
stored as VARCHAR, native UUID columns, and whether a timestamp keeps its
offset. So these run the real migrations against a real PostgreSQL and then
re-check the rules that matter.

Skipped unless TEST_DATABASE_URL is set. CI always sets it. Locally:

    podman run -d --rm --name hextime-pg -p 55432:5432 \\
        -e POSTGRES_PASSWORD=hextime docker.io/library/postgres:17-alpine

    TEST_DATABASE_URL=postgresql+psycopg://postgres:hextime@127.0.0.1:55432/postgres \\
        uv run pytest tests/test_postgres.py
"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Project, Tag, Team, TeamMember, TeamRole, TimeEntry, User
from app.services import entries, reports
from app.services import projects as projects_service
from app.services import tags as tags_service
from app.services.reports import GroupBy
from tests.conftest import POSTGRES_URL, alembic_config, requires_postgres

pytestmark = requires_postgres

HELSINKI = "Europe/Helsinki"


def make_user(pg: Session, name: str = "Test User") -> User:
    user = User(display_name=name)
    pg.add(user)
    pg.commit()
    return user


def at(hour: int, day: int = 4, month: int = 5) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


# ---------------------------------------------------------------------------
# The migrations describe the same schema on PostgreSQL
# ---------------------------------------------------------------------------


def test_migrations_create_every_table_and_column(postgres_engine: Engine) -> None:
    from app.models import Base

    inspector = inspect(postgres_engine)
    tables = {name for name in inspector.get_table_names() if name != "alembic_version"}

    assert tables == set(Base.metadata.tables)

    for name, table in Base.metadata.tables.items():
        actual = {column["name"] for column in inspector.get_columns(name)}
        assert actual == {column.name for column in table.columns}, name


def test_uuid_keys_use_the_native_type(postgres_engine: Engine) -> None:
    """SQLAlchemy's Uuid maps to CHAR on SQLite but to real UUID here."""
    columns = {c["name"]: c for c in inspect(postgres_engine).get_columns("time_entries")}

    assert type(columns["id"]["type"]).__name__ == "UUID"


def test_timestamps_are_stored_with_a_time_zone(postgres_engine: Engine) -> None:
    columns = {c["name"]: c for c in inspect(postgres_engine).get_columns("time_entries")}

    assert columns["started_at"]["type"].timezone is True


def test_downgrade_removes_everything(postgres_engine: Engine) -> None:
    from alembic import command

    command.downgrade(alembic_config(POSTGRES_URL), "base")

    engine = create_engine(POSTGRES_URL)
    remaining = [name for name in inspect(engine).get_table_names() if name != "alembic_version"]
    engine.dispose()

    assert remaining == []


# ---------------------------------------------------------------------------
# Constraints the desktop build relies on must bite here too
# ---------------------------------------------------------------------------


def test_only_one_running_timer_per_user(pg: Session) -> None:
    """The partial unique index. Autogenerate drops the WHERE clause easily,
    and on PostgreSQL that would forbid a second entry entirely."""
    user = make_user(pg)
    pg.add(TimeEntry(user_id=user.id, started_at=at(8)))
    pg.commit()

    pg.add(TimeEntry(user_id=user.id, started_at=at(9)))
    with pytest.raises(IntegrityError):
        pg.commit()


def test_many_finished_entries_are_allowed(pg: Session) -> None:
    user = make_user(pg)
    pg.add(TimeEntry(user_id=user.id, started_at=at(8), ended_at=at(9)))
    pg.add(TimeEntry(user_id=user.id, started_at=at(10), ended_at=at(11)))
    pg.commit()

    assert len(pg.scalars(select(TimeEntry)).all()) == 2


def test_exactly_one_owner_is_enforced(pg: Session) -> None:
    pg.add(Project(name="Orphan"))

    with pytest.raises(IntegrityError):
        pg.commit()


def test_an_entry_must_end_after_it_starts(pg: Session) -> None:
    user = make_user(pg)
    pg.add(TimeEntry(user_id=user.id, started_at=at(10), ended_at=at(9)))

    with pytest.raises(IntegrityError):
        pg.commit()


def test_foreign_keys_are_enforced(pg: Session) -> None:
    pg.add(TimeEntry(user_id=uuid4(), started_at=at(10), ended_at=at(11)))

    with pytest.raises(IntegrityError):
        pg.commit()


def test_a_team_role_is_stored_as_its_lowercase_value(pg: Session) -> None:
    user = make_user(pg)
    team = Team(name="Devs", created_by=user.id)
    pg.add(team)
    pg.commit()
    pg.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.LEAD))
    pg.commit()

    assert pg.execute(text("SELECT role FROM team_members")).scalar_one() == "lead"


def test_an_unknown_team_role_is_refused(pg: Session) -> None:
    """native_enum=False stores a VARCHAR plus a CHECK. The CHECK is the part
    that keeps a typo out of the column."""
    user = make_user(pg)
    team = Team(name="Devs", created_by=user.id)
    pg.add(team)
    pg.commit()

    with pytest.raises(IntegrityError):
        pg.execute(
            text(
                "INSERT INTO team_members (team_id, user_id, role, joined_at) "
                "VALUES (:team, :user, 'overlord', now())"
            ),
            {"team": team.id, "user": user.id},
        )
        pg.commit()


# ---------------------------------------------------------------------------
# UTC in, UTC out
# ---------------------------------------------------------------------------


def test_a_local_time_comes_back_as_the_same_instant_in_utc(pg: Session) -> None:
    user = make_user(pg)
    helsinki_noon = datetime(2026, 7, 1, 12, tzinfo=timezone(timedelta(hours=3)))
    entry = TimeEntry(
        user_id=user.id, started_at=helsinki_noon, ended_at=helsinki_noon + timedelta(hours=1)
    )
    pg.add(entry)
    pg.commit()
    entry_id = entry.id

    pg.expire_all()
    loaded = pg.get(TimeEntry, entry_id)

    assert loaded is not None
    assert loaded.started_at == helsinki_noon
    assert loaded.started_at.tzinfo is not None
    assert loaded.started_at.astimezone(UTC).hour == 9


def test_a_naive_timestamp_is_still_refused(pg: Session) -> None:
    from sqlalchemy.exc import StatementError

    user = make_user(pg)
    pg.add(TimeEntry(user_id=user.id, started_at=datetime(2026, 5, 4, 10)))

    with pytest.raises(StatementError, match="naive datetime"):
        pg.commit()


# ---------------------------------------------------------------------------
# The services and reports run unchanged
# ---------------------------------------------------------------------------


def test_the_service_layer_runs_unchanged(pg: Session) -> None:
    """Nothing in the services is SQLite-specific — the proof rather than the
    assumption."""
    user = make_user(pg)
    project = projects_service.create_project(
        pg, user=user, name="Client", hourly_rate_cents=8500, billable_default=True
    )
    tag = tags_service.create_tag(pg, user=user, name="urgent")

    entry = entries.create_entry(
        pg,
        user=user,
        started_at=at(9),
        ended_at=at(11),
        project_id=project.id,
        tag_ids=[tag.id],
    )

    assert entry.duration_seconds == 7200
    assert entry.rate_snapshot_cents == 8500
    assert [t.name for t in entry.tags] == ["urgent"]


def test_the_overlap_check_works_the_same(pg: Session) -> None:
    user = make_user(pg)
    entries.create_entry(pg, user=user, started_at=at(10), ended_at=at(11))

    from app.core.errors import EntryOverlapError

    with pytest.raises(EntryOverlapError):
        entries.create_entry(pg, user=user, started_at=at(10, 4), ended_at=at(12))


def test_reports_group_by_the_users_local_day(pg: Session) -> None:
    """The same daylight-saving case as on SQLite: 22:30 UTC on 28 March is
    00:30 on 29 March in Helsinki. The range filter runs in SQL here."""
    user = make_user(pg)
    entries.create_entry(
        pg,
        user=user,
        started_at=datetime(2026, 3, 28, 22, 30, tzinfo=UTC),
        ended_at=datetime(2026, 3, 28, 23, 30, tzinfo=UTC),
    )
    start = datetime(2026, 3, 23, tzinfo=timezone(timedelta(hours=2)))
    end = datetime(2026, 3, 30, tzinfo=timezone(timedelta(hours=3)))

    summary = reports.summarize(
        pg, user=user, starts_from=start, starts_before=end, group_by=GroupBy.DAY, tz=HELSINKI
    )

    assert len(summary.groups) == 7
    assert [g.key for g in summary.groups if g.total_seconds] == ["2026-03-29"]
    assert summary.total_seconds == 3600


def test_report_money_rounds_once_here_too(pg: Session) -> None:
    user = make_user(pg)
    project = projects_service.create_project(
        pg, user=user, name="Client", hourly_rate_cents=8500, billable_default=True
    )
    for hour in (8, 9, 10):
        entries.create_entry(
            pg,
            user=user,
            started_at=at(hour),
            ended_at=at(hour) + timedelta(minutes=20),
            project_id=project.id,
        )

    summary = reports.summarize(
        pg,
        user=user,
        starts_from=at(0),
        starts_before=at(0) + timedelta(days=1),
        group_by=GroupBy.DAY,
    )

    assert summary.billable_amount_cents == 8500


def test_ownership_still_hides_other_peoples_rows(pg: Session) -> None:
    mine = make_user(pg, "Mine")
    theirs = make_user(pg, "Theirs")
    project = projects_service.create_project(pg, user=theirs, name="Theirs")

    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        projects_service.get_project(pg, project.id, mine)


def test_a_tag_belongs_to_its_owner_only(pg: Session) -> None:
    mine = make_user(pg, "Mine")
    theirs = make_user(pg, "Theirs")
    tag = Tag(name="theirs", owner_user_id=theirs.id)
    pg.add(tag)
    pg.commit()

    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        tags_service.get_tag(pg, tag.id, mine)
