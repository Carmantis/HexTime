"""The rules the database itself enforces.

These are deliberately tested against a real SQLite database rather than by
inspecting the model classes: a constraint that is declared but never emitted
would still pass a class-level test.
"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import Project, Tag, Team, TeamMember, TeamRole, TimeEntry, User


def make_user(db: Session, name: str = "Test User") -> User:
    user = User(display_name=name)
    db.add(user)
    db.commit()
    return user


def make_team(db: Session, owner: User) -> Team:
    team = Team(name="Test Team", created_by=owner.id)
    db.add(team)
    db.commit()
    return team


def start(db: Session, user: User, at: datetime, ended: datetime | None = None) -> TimeEntry:
    entry = TimeEntry(user_id=user.id, started_at=at, ended_at=ended)
    db.add(entry)
    db.commit()
    return entry


# --------------------------------------------------------------------------
# UTC handling
# --------------------------------------------------------------------------


def test_naive_datetime_is_rejected(db: Session) -> None:
    """A naive datetime is ambiguous, so it must never reach the database."""
    user = make_user(db)
    db.add(TimeEntry(user_id=user.id, started_at=datetime(2026, 3, 29, 12, 0)))

    with pytest.raises(StatementError, match="naive datetime"):
        db.commit()


def test_aware_utc_datetime_round_trips(db: Session) -> None:
    user = make_user(db)
    started = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)
    entry_id = start(db, user, started).id

    db.expire_all()
    loaded = db.get(TimeEntry, entry_id)

    assert loaded is not None
    assert loaded.started_at == started
    assert loaded.started_at.tzinfo is not None


def test_local_time_is_converted_to_utc(db: Session) -> None:
    """Finnish summer time is UTC+3; the stored instant must be the same."""
    user = make_user(db)
    helsinki_noon = datetime(2026, 7, 1, 12, 0, tzinfo=timezone(timedelta(hours=3)))
    entry_id = start(db, user, helsinki_noon).id

    db.expire_all()
    loaded = db.get(TimeEntry, entry_id)

    assert loaded is not None
    assert loaded.started_at == helsinki_noon
    assert loaded.started_at.hour == 9  # same instant, expressed in UTC


def test_duration_spans_a_dst_change(db: Session) -> None:
    """DST in Helsinki 2026 starts 29 March 03:00 local. Stored in UTC, an
    hour-long entry across it is still exactly one hour."""
    user = make_user(db)
    before = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    after = datetime(2026, 3, 29, 1, 30, tzinfo=UTC)

    entry = start(db, user, before, after)

    assert entry.duration == timedelta(hours=1)
    assert entry.duration_seconds == 3600


# --------------------------------------------------------------------------
# Ownership: exactly one of user or team
# --------------------------------------------------------------------------


def test_project_rejects_having_no_owner(db: Session) -> None:
    db.add(Project(name="Orphan"))

    with pytest.raises(IntegrityError):
        db.commit()


def test_project_rejects_having_two_owners(db: Session) -> None:
    user = make_user(db)
    team = make_team(db, user)
    db.add(Project(name="Both", owner_user_id=user.id, owner_team_id=team.id))

    with pytest.raises(IntegrityError):
        db.commit()


def test_project_accepts_a_user_owner(db: Session) -> None:
    user = make_user(db)
    db.add(Project(name="Mine", owner_user_id=user.id))
    db.commit()

    assert db.scalar(select(Project).where(Project.name == "Mine")) is not None


def test_project_accepts_a_team_owner(db: Session) -> None:
    user = make_user(db)
    team = make_team(db, user)
    db.add(Project(name="Ours", owner_team_id=team.id))
    db.commit()

    assert db.scalar(select(Project).where(Project.name == "Ours")) is not None


def test_tag_follows_the_same_ownership_rule(db: Session) -> None:
    db.add(Tag(name="orphan-tag"))

    with pytest.raises(IntegrityError):
        db.commit()


# --------------------------------------------------------------------------
# Timer rules
# --------------------------------------------------------------------------


def test_only_one_running_timer_per_user(db: Session) -> None:
    user = make_user(db)
    start(db, user, datetime(2026, 1, 1, 8, 0, tzinfo=UTC))

    db.add(TimeEntry(user_id=user.id, started_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC)))

    with pytest.raises(IntegrityError):
        db.commit()


def test_two_users_may_each_run_a_timer(db: Session) -> None:
    first = make_user(db, "First")
    second = make_user(db, "Second")
    at = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    start(db, first, at)
    start(db, second, at)

    running = db.scalars(select(TimeEntry).where(TimeEntry.ended_at.is_(None))).all()
    assert len(running) == 2


def test_many_finished_entries_are_allowed(db: Session) -> None:
    """The unique index is partial: it only constrains running timers."""
    user = make_user(db)
    day = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    start(db, user, day, day + timedelta(hours=1))
    start(db, user, day + timedelta(hours=2), day + timedelta(hours=3))

    assert len(db.scalars(select(TimeEntry)).all()) == 2


def test_entry_must_end_after_it_starts(db: Session) -> None:
    user = make_user(db)
    at = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    db.add(TimeEntry(user_id=user.id, started_at=at, ended_at=at - timedelta(minutes=1)))

    with pytest.raises(IntegrityError):
        db.commit()


def test_running_entry_has_no_duration(db: Session) -> None:
    user = make_user(db)
    entry = start(db, user, datetime(2026, 1, 1, 8, 0, tzinfo=UTC))

    assert entry.is_running
    assert entry.duration is None
    assert entry.duration_seconds is None


# --------------------------------------------------------------------------
# Referential integrity and enums
# --------------------------------------------------------------------------


def test_foreign_keys_are_enforced_on_sqlite(db: Session) -> None:
    """Guards the PRAGMA in core/db.py: without it SQLite ignores this."""
    db.add(TimeEntry(user_id=uuid4(), started_at=datetime(2026, 1, 1, tzinfo=UTC)))

    with pytest.raises(IntegrityError):
        db.commit()


def test_team_role_is_stored_as_its_lowercase_value(db: Session) -> None:
    user = make_user(db)
    team = make_team(db, user)
    db.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.LEAD))
    db.commit()

    stored = db.execute(text("SELECT role FROM team_members")).scalar_one()
    assert stored == "lead"


def test_archived_records_keep_their_row(db: Session) -> None:
    """Archive, never delete, so old entries keep their project name."""
    user = make_user(db)
    project = Project(name="Old", owner_user_id=user.id)
    db.add(project)
    db.commit()

    assert project.archived_at is None
    project.archived_at = datetime(2026, 1, 1, tzinfo=UTC)
    db.commit()

    assert db.get(Project, project.id) is not None
