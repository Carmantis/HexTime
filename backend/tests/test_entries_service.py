"""Time entry service rules.

The heart of this file is the overlap policy: entries are billed, so two
entries of the same user may never cover the same moment.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import EntryOverlapError, NotFoundError, ValidationFailedError
from app.models import AuditLog, Project, Task, TimeEntry, User
from app.services import audit, entries


def at(hour: int, minute: int = 0) -> datetime:
    """A time on one arbitrary but fixed day, in UTC."""
    return datetime(2026, 5, 4, hour, minute, tzinfo=UTC)


def audit_rows(db: Session, action: str) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action)))


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------

OVERLAP_CASES = [
    pytest.param(at(10), at(11), False, id="identical"),
    pytest.param(at(10, 15), at(10, 45), False, id="contained"),
    pytest.param(at(9, 30), at(11, 30), False, id="straddling"),
    pytest.param(at(9, 30), at(10, 30), False, id="overlaps-start"),
    pytest.param(at(10, 30), at(11, 30), False, id="overlaps-end"),
    pytest.param(at(9), at(10), True, id="ends-exactly-when-base-starts"),
    pytest.param(at(11), at(12), True, id="starts-exactly-when-base-ends"),
    pytest.param(at(8), at(9), True, id="entirely-before"),
    pytest.param(at(13), at(14), True, id="entirely-after"),
]


@pytest.mark.parametrize(("start", "end", "allowed"), OVERLAP_CASES)
def test_overlap_policy(
    db: Session, user: User, start: datetime, end: datetime, *, allowed: bool
) -> None:
    """Ranges are half-open, so touching entries are fine but sharing a
    single minute is not."""
    entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))

    if allowed:
        created = entries.create_entry(db, user=user, started_at=start, ended_at=end)
        assert created.id is not None
    else:
        with pytest.raises(EntryOverlapError):
            entries.create_entry(db, user=user, started_at=start, ended_at=end)


def test_another_users_entry_never_overlaps(db: Session, user: User, other_user: User) -> None:
    """Two people may of course work at the same time."""
    entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))

    created = entries.create_entry(db, user=other_user, started_at=at(10), ended_at=at(11))

    assert created.user_id == other_user.id


def test_a_running_entry_blocks_everything_after_it(db: Session, user: User) -> None:
    """A running timer has no end, so it covers all later time."""
    entries.create_entry(db, user=user, started_at=at(10))

    with pytest.raises(EntryOverlapError):
        entries.create_entry(db, user=user, started_at=at(14), ended_at=at(15))


def test_a_running_entry_allows_earlier_entries(db: Session, user: User) -> None:
    entries.create_entry(db, user=user, started_at=at(10))

    created = entries.create_entry(db, user=user, started_at=at(8), ended_at=at(9))

    assert created.duration == timedelta(hours=1)


def test_entry_must_end_after_it_starts(db: Session, user: User) -> None:
    with pytest.raises(ValidationFailedError):
        entries.create_entry(db, user=user, started_at=at(11), ended_at=at(10))


# ---------------------------------------------------------------------------
# Rate snapshot and billing defaults
# ---------------------------------------------------------------------------


def test_entry_inherits_the_projects_billing_defaults(
    db: Session, user: User, project: Project
) -> None:
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), project_id=project.id
    )

    assert entry.billable is True
    assert entry.rate_snapshot_cents == 8500
    assert entry.currency == "EUR"


def test_caller_may_override_the_billable_default(
    db: Session, user: User, project: Project
) -> None:
    entry = entries.create_entry(
        db,
        user=user,
        started_at=at(10),
        ended_at=at(11),
        project_id=project.id,
        billable=False,
    )

    assert entry.billable is False


def test_changing_the_project_rate_does_not_rewrite_old_entries(
    db: Session, user: User, project: Project
) -> None:
    """The reason rate_snapshot_cents exists at all."""
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), project_id=project.id
    )

    project.hourly_rate_cents = 12000
    db.commit()
    db.expire_all()

    assert db.get(TimeEntry, entry.id).rate_snapshot_cents == 8500


def test_entry_without_a_project_has_no_rate(db: Session, user: User) -> None:
    entry = entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))

    assert entry.rate_snapshot_cents is None
    assert entry.billable is False


def test_task_must_belong_to_the_given_project(db: Session, user: User, project: Project) -> None:
    stray = Project(name="Other", owner_user_id=user.id)
    db.add(stray)
    db.commit()
    task = Task(project_id=stray.id, name="Design")
    db.add(task)
    db.commit()

    with pytest.raises(ValidationFailedError):
        entries.create_entry(
            db,
            user=user,
            started_at=at(10),
            ended_at=at(11),
            project_id=project.id,
            task_id=task.id,
        )


def test_unknown_project_is_not_found(db: Session, user: User) -> None:
    from uuid import uuid4

    with pytest.raises(NotFoundError):
        entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11), project_id=uuid4())


# ---------------------------------------------------------------------------
# Updating
# ---------------------------------------------------------------------------


def test_an_entry_may_be_moved_onto_its_own_old_time(db: Session, user: User) -> None:
    """The overlap check must not see the entry being edited as a conflict."""
    entry = entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))

    entries.update_entry(db, entry=entry, actor=user, started_at=at(10, 30))

    assert entry.started_at == at(10, 30)


def test_update_rejects_moving_an_entry_onto_another(db: Session, user: User) -> None:
    entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))
    second = entries.create_entry(db, user=user, started_at=at(12), ended_at=at(13))

    with pytest.raises(EntryOverlapError):
        entries.update_entry(db, entry=second, actor=user, started_at=at(10, 30))


def test_omitted_fields_are_left_alone(db: Session, user: User) -> None:
    """Guards the UNSET sentinel: not passing a field must not clear it."""
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), description="original"
    )

    entries.update_entry(db, entry=entry, actor=user, billable=True)

    assert entry.description == "original"
    assert entry.billable is True


def test_a_field_can_be_explicitly_cleared(db: Session, user: User) -> None:
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), description="original"
    )

    entries.update_entry(db, entry=entry, actor=user, description=None)

    assert entry.description is None


def test_moving_an_entry_to_another_project_rereads_the_rate(
    db: Session, user: User, project: Project
) -> None:
    cheaper = Project(name="Cheap", owner_user_id=user.id, hourly_rate_cents=5000)
    db.add(cheaper)
    db.commit()
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), project_id=project.id
    )

    entries.update_entry(db, entry=entry, actor=user, project_id=cheaper.id)

    assert entry.rate_snapshot_cents == 5000


def test_entries_of_other_users_are_not_found(db: Session, user: User, other_user: User) -> None:
    entry = entries.create_entry(db, user=other_user, started_at=at(10), ended_at=at(11))

    with pytest.raises(NotFoundError):
        entries.get_entry(db, entry.id, user)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def test_creating_an_entry_is_audited(db: Session, user: User) -> None:
    entry = entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))

    rows = audit_rows(db, audit.ACTION_CREATE)
    assert len(rows) == 1
    assert rows[0].entity_id == entry.id
    assert rows[0].actor_user_id == user.id
    assert rows[0].before_json is None
    assert rows[0].after_json is not None


def test_updating_an_entry_records_before_and_after(db: Session, user: User) -> None:
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), description="before"
    )

    entries.update_entry(db, entry=entry, actor=user, description="after")

    rows = audit_rows(db, audit.ACTION_UPDATE)
    assert len(rows) == 1
    assert '"before"' in rows[0].before_json
    assert '"after"' in rows[0].after_json


def test_deleting_an_entry_leaves_its_last_state_behind(db: Session, user: User) -> None:
    entry = entries.create_entry(
        db, user=user, started_at=at(10), ended_at=at(11), description="gone"
    )
    entry_id = entry.id

    entries.delete_entry(db, entry=entry, actor=user)

    assert db.get(TimeEntry, entry_id) is None
    rows = audit_rows(db, audit.ACTION_DELETE)
    assert len(rows) == 1
    assert '"gone"' in rows[0].before_json


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_listing_filters_by_time_range(db: Session, user: User) -> None:
    entries.create_entry(db, user=user, started_at=at(8), ended_at=at(9))
    entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11))
    entries.create_entry(db, user=user, started_at=at(12), ended_at=at(13))

    found = entries.list_entries(db, user_id=user.id, starts_from=at(10), starts_before=at(12))

    assert [entry.started_at for entry in found] == [at(10)]


def test_listing_returns_newest_first(db: Session, user: User) -> None:
    entries.create_entry(db, user=user, started_at=at(8), ended_at=at(9))
    entries.create_entry(db, user=user, started_at=at(12), ended_at=at(13))

    found = entries.list_entries(db, user_id=user.id)

    assert [entry.started_at for entry in found] == [at(12), at(8)]


def test_listing_filters_by_project(db: Session, user: User, project: Project) -> None:
    entries.create_entry(db, user=user, started_at=at(10), ended_at=at(11), project_id=project.id)
    entries.create_entry(db, user=user, started_at=at(12), ended_at=at(13))

    found = entries.list_entries(db, user_id=user.id, project_id=project.id)

    assert len(found) == 1
    assert found[0].project_id == project.id


def test_listing_never_leaks_another_users_entries(
    db: Session, user: User, other_user: User
) -> None:
    entries.create_entry(db, user=other_user, started_at=at(10), ended_at=at(11))

    assert entries.list_entries(db, user_id=user.id) == []
