"""Timer service rules.

A running timer is just an entry with no end, so these tests also check that
starting and stopping leaves the entry table in a state the reports can trust.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import TimerNotRunningError, ValidationFailedError
from app.models import AuditLog, Project, TimeEntry, User
from app.services import timer


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 4, hour, minute, tzinfo=UTC)


def test_nothing_is_running_at_first(db: Session, user: User) -> None:
    assert timer.get_running(db, user.id) is None


def test_start_creates_a_running_entry(db: Session, user: User) -> None:
    entry = timer.start(db, user=user, at=at(9), description="Writing docs")

    assert entry.is_running
    assert entry.ended_at is None
    assert entry.duration is None
    assert timer.get_running(db, user.id) == entry


def test_stop_finishes_the_entry(db: Session, user: User) -> None:
    timer.start(db, user=user, at=at(9))

    stopped = timer.stop(db, user=user, at=at(11))

    assert stopped.ended_at == at(11)
    assert stopped.duration == timedelta(hours=2)
    assert timer.get_running(db, user.id) is None


def test_starting_a_second_timer_stops_the_first(db: Session, user: User) -> None:
    """Plan rule: starting a new timer stops the previous one."""
    first = timer.start(db, user=user, at=at(9))

    second = timer.start(db, user=user, at=at(10))

    assert first.ended_at == at(10)
    assert second.is_running
    assert timer.get_running(db, user.id) == second


def test_only_one_entry_is_ever_running(db: Session, user: User) -> None:
    timer.start(db, user=user, at=at(9))
    timer.start(db, user=user, at=at(10))
    timer.start(db, user=user, at=at(11))

    running = db.scalars(select(TimeEntry).where(TimeEntry.ended_at.is_(None))).all()
    assert len(running) == 1


def test_two_users_may_each_run_a_timer(db: Session, user: User, other_user: User) -> None:
    timer.start(db, user=user, at=at(9))
    timer.start(db, user=other_user, at=at(9))

    assert timer.get_running(db, user.id) is not None
    assert timer.get_running(db, other_user.id) is not None


def test_stopping_nothing_is_an_error(db: Session, user: User) -> None:
    with pytest.raises(TimerNotRunningError):
        timer.stop(db, user=user)


def test_a_timer_cannot_end_before_it_started(db: Session, user: User) -> None:
    timer.start(db, user=user, at=at(11))

    with pytest.raises(ValidationFailedError):
        timer.stop(db, user=user, at=at(10))


def test_stopping_at_the_exact_start_is_refused(db: Session, user: User) -> None:
    """A zero-length entry would violate the database CHECK; refusing is
    better than inventing a duration."""
    timer.start(db, user=user, at=at(9))

    with pytest.raises(ValidationFailedError):
        timer.stop(db, user=user, at=at(9))


def test_started_timer_inherits_project_defaults(db: Session, user: User, project: Project) -> None:
    entry = timer.start(db, user=user, at=at(9), project_id=project.id)

    assert entry.billable is True
    assert entry.rate_snapshot_cents == 8500


def test_stopping_is_audited(db: Session, user: User) -> None:
    timer.start(db, user=user, at=at(9))

    timer.stop(db, user=user, at=at(10))

    updates = db.scalars(select(AuditLog).where(AuditLog.action == "update")).all()
    assert len(updates) == 1
    assert '"ended_at": null' in updates[0].before_json
    assert '"ended_at": null' not in updates[0].after_json


def test_the_handover_between_two_timers_leaves_no_gap(db: Session, user: User) -> None:
    """The first entry ends exactly when the second begins, which the
    half-open overlap rule allows."""
    first = timer.start(db, user=user, at=at(9))
    second = timer.start(db, user=user, at=at(10))

    assert first.ended_at == second.started_at
