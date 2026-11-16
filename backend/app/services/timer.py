"""The running timer.

A running timer is simply a time entry whose ``ended_at`` is still NULL. There
is no separate timer table, so the timer can never disagree with the entry it
will become.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import TimerNotRunningError, ValidationFailedError
from app.models import TimeEntry, User
from app.models.base import utc_now
from app.services import audit, entries


def get_running(db: Session, user_id: UUID) -> TimeEntry | None:
    """The user's running entry, or None. A partial unique index in the
    database guarantees there can never be more than one."""
    return db.scalars(
        select(TimeEntry).where(TimeEntry.user_id == user_id, TimeEntry.ended_at.is_(None))
    ).first()


def start(
    db: Session,
    *,
    user: User,
    project_id: UUID | None = None,
    task_id: UUID | None = None,
    description: str | None = None,
    billable: bool | None = None,
    tag_ids: Sequence[UUID] | None = None,
    at: datetime | None = None,
) -> TimeEntry:
    """Start a timer, stopping whatever was already running for this user."""
    now = at or utc_now()

    if get_running(db, user.id) is not None:
        stop(db, user=user, at=now)

    return entries.create_entry(
        db,
        user=user,
        started_at=now,
        project_id=project_id,
        task_id=task_id,
        description=description,
        billable=billable,
        tag_ids=tag_ids,
    )


#: How far back the browser may date a stop. Enough to ride out a server
#: restart or a dropped connection; not a way to rewrite the afternoon.
MAX_CLIENT_STOP_AGE = timedelta(minutes=10)
#: Clocks are never quite in step; a stop dated slightly ahead is accepted.
CLOCK_SKEW = timedelta(minutes=1)


def stop_at_client_time(db: Session, *, user: User, at: datetime) -> TimeEntry:
    """Stop the timer at the moment the user pressed Stop, sent by the browser.

    When the server is briefly unreachable (an update, a dropped connection)
    the browser retries with the time of the original click, so the entry
    does not run on for however long the outage lasted.
    """
    now = utc_now()
    if at > now + CLOCK_SKEW or at < now - MAX_CLIENT_STOP_AGE:
        raise ValidationFailedError("the stop time is too far from now")
    return stop(db, user=user, at=min(at, now))


def stop(db: Session, *, user: User, at: datetime | None = None) -> TimeEntry:
    """Stop the running timer and return the finished entry."""
    running = get_running(db, user.id)
    if running is None:
        raise TimerNotRunningError("no timer is running")

    now = at or utc_now()
    if now <= running.started_at:
        # The database CHECK requires ended_at > started_at. Refusing is
        # honest; silently inventing a duration would not be.
        raise ValidationFailedError("a timer cannot end before it started")

    before = audit.entry_snapshot(running)
    running.ended_at = now
    db.flush()

    audit.record(
        db,
        actor_user_id=user.id,
        entity_type=audit.ENTITY_TIME_ENTRY,
        entity_id=running.id,
        action=audit.ACTION_UPDATE,
        before=before,
        after=audit.entry_snapshot(running),
    )
    db.commit()
    return running
