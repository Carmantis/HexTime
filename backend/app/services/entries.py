"""Time entry business logic.

Services take a Session and plain arguments, never a Request, which is what
makes them testable without HTTP.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import EntryOverlapError, NotFoundError, ValidationFailedError
from app.models import Project, Tag, Task, TimeEntry, User
from app.services import audit, ownership
from app.services.sentinel import UNSET, Unset


def _load_project(db: Session, project_id: UUID, user: User) -> Project:
    """Load a project this user is allowed to book time on: their own, or one
    of a team they are in (services/ownership.py)."""
    return ownership.require_visible(db, db.get(Project, project_id), user, "project")


def _load_task(db: Session, task_id: UUID, project: Project | None) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("task not found")
    if project is None or task.project_id != project.id:
        raise ValidationFailedError("task does not belong to the given project")
    return task


def _load_tags(db: Session, tag_ids: Sequence[UUID] | None, user: User) -> list[Tag]:
    """The caller's tags, deduplicated and sorted by name.

    Tags are a set: the order they are sent in carries no meaning, and the
    relationship would not preserve it anyway. Sorting here means a freshly
    assigned list and one reloaded from the database always look the same.

    A tag that does not exist and a tag belonging to someone else give the
    same answer, so the API cannot be used to find out which ids are real.
    """
    wanted = list(dict.fromkeys(tag_ids or []))
    if not wanted:
        return []

    found = {
        tag.id: tag
        for tag in db.scalars(
            select(Tag).where(Tag.id.in_(wanted), ownership.visible_to(Tag, user))
        )
    }
    if len(found) != len(wanted):
        raise NotFoundError("tag not found")

    return sorted(found.values(), key=lambda tag: tag.name)


def find_overlapping(
    db: Session,
    *,
    user_id: UUID,
    started_at: datetime,
    ended_at: datetime | None,
    exclude_id: UUID | None = None,
) -> TimeEntry | None:
    """Return an entry of the same user covering part of the same time.

    Ranges are half-open: an entry ending exactly when the next begins does not
    overlap. A running entry has no end, so it is treated as reaching forever;
    that is why ``ended_at IS NULL`` counts as "ends after anything".
    """
    stmt: Select[tuple[TimeEntry]] = select(TimeEntry).where(TimeEntry.user_id == user_id)

    if exclude_id is not None:
        stmt = stmt.where(TimeEntry.id != exclude_id)

    # The existing entry ends after the new one starts ...
    stmt = stmt.where(or_(TimeEntry.ended_at.is_(None), TimeEntry.ended_at > started_at))
    # ... and begins before the new one ends.
    stmt = stmt.where(TimeEntry.started_at < ended_at if ended_at is not None else true())

    return db.scalars(stmt.limit(1)).first()


def _guard_range(started_at: datetime, ended_at: datetime | None) -> None:
    if ended_at is not None and ended_at <= started_at:
        raise ValidationFailedError("ended_at must be after started_at")


def _guard_overlap(
    db: Session,
    *,
    user_id: UUID,
    started_at: datetime,
    ended_at: datetime | None,
    exclude_id: UUID | None = None,
) -> None:
    clash = find_overlapping(
        db,
        user_id=user_id,
        started_at=started_at,
        ended_at=ended_at,
        exclude_id=exclude_id,
    )
    if clash is not None:
        raise EntryOverlapError("this time is already covered by another entry")


def create_entry(
    db: Session,
    *,
    user: User,
    started_at: datetime,
    ended_at: datetime | None = None,
    project_id: UUID | None = None,
    task_id: UUID | None = None,
    description: str | None = None,
    billable: bool | None = None,
    tag_ids: Sequence[UUID] | None = None,
) -> TimeEntry:
    """Create an entry, copying the project's rate into it."""
    _guard_range(started_at, ended_at)
    _guard_overlap(db, user_id=user.id, started_at=started_at, ended_at=ended_at)

    project = _load_project(db, project_id, user) if project_id else None
    if task_id is not None:
        _load_task(db, task_id, project)

    entry = TimeEntry(
        user_id=user.id,
        project_id=project.id if project else None,
        task_id=task_id,
        description=description,
        started_at=started_at,
        ended_at=ended_at,
        # The project decides unless the caller says otherwise.
        billable=billable if billable is not None else bool(project and project.billable_default),
        # Frozen now: changing the project rate later must not rewrite history.
        rate_snapshot_cents=project.hourly_rate_cents if project else None,
        currency=project.currency if project else "EUR",
    )
    entry.tags = _load_tags(db, tag_ids, user)
    db.add(entry)
    db.flush()  # assigns entry.id so the audit row can point at it

    audit.record(
        db,
        actor_user_id=user.id,
        entity_type=audit.ENTITY_TIME_ENTRY,
        entity_id=entry.id,
        action=audit.ACTION_CREATE,
        after=audit.entry_snapshot(entry),
    )
    db.commit()
    return entry


def get_entry(db: Session, entry_id: UUID, user: User) -> TimeEntry:
    """One of the user's own entries. Nobody else's, whatever their role."""
    entry = db.get(TimeEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        raise NotFoundError("time entry not found")
    return entry


def update_entry(
    db: Session,
    *,
    entry: TimeEntry,
    actor: User,
    started_at: datetime | None = None,
    ended_at: datetime | Unset | None = UNSET,
    project_id: UUID | Unset | None = UNSET,
    task_id: UUID | Unset | None = UNSET,
    description: str | Unset | None = UNSET,
    billable: bool | None = None,
    tag_ids: Sequence[UUID] | Unset | None = UNSET,
) -> TimeEntry:
    """Apply a partial change to an entry and write it to the audit log.

    ``ended_at``, ``project_id``, ``task_id`` and ``description`` use the UNSET
    sentinel so that explicitly clearing them to None is possible.
    """
    before = audit.entry_snapshot(entry)

    new_start = started_at if started_at is not None else entry.started_at
    new_end = entry.ended_at if isinstance(ended_at, Unset) else ended_at

    _guard_range(new_start, new_end)
    _guard_overlap(
        db,
        user_id=entry.user_id,
        started_at=new_start,
        ended_at=new_end,
        exclude_id=entry.id,
    )

    entry.started_at = new_start
    if not isinstance(ended_at, Unset):
        entry.ended_at = ended_at
    if not isinstance(description, Unset):
        entry.description = description
    if billable is not None:
        entry.billable = billable

    # Only an actual change of project counts. A form that re-sends the same
    # project on every save must not re-read the rate: that would silently
    # rewrite an old entry's rate_snapshot_cents after the project's rate
    # changed, which is exactly what the snapshot exists to prevent.
    if not isinstance(project_id, Unset) and project_id != entry.project_id:
        project = _load_project(db, project_id, actor) if project_id else None
        entry.project_id = project.id if project else None
        # Moving an entry to another project re-reads that project's rate.
        entry.rate_snapshot_cents = project.hourly_rate_cents if project else None
        entry.currency = project.currency if project else "EUR"
        # The old task belonged to the old project, so it cannot survive.
        entry.task_id = None

    if not isinstance(task_id, Unset):
        if task_id is None:
            entry.task_id = None
        else:
            project = db.get(Project, entry.project_id) if entry.project_id else None
            _load_task(db, task_id, project)
            entry.task_id = task_id

    if not isinstance(tag_ids, Unset):
        # Replaces the whole set. Both null and [] mean "no tags at all".
        entry.tags = _load_tags(db, tag_ids, actor)

    db.flush()
    audit.record(
        db,
        actor_user_id=actor.id,
        entity_type=audit.ENTITY_TIME_ENTRY,
        entity_id=entry.id,
        action=audit.ACTION_UPDATE,
        before=before,
        after=audit.entry_snapshot(entry),
    )
    db.commit()
    return entry


def delete_entry(db: Session, *, entry: TimeEntry, actor: User) -> None:
    """Delete an entry, leaving its last known state in the audit log."""
    audit.record(
        db,
        actor_user_id=actor.id,
        entity_type=audit.ENTITY_TIME_ENTRY,
        entity_id=entry.id,
        action=audit.ACTION_DELETE,
        before=audit.entry_snapshot(entry),
    )
    db.delete(entry)
    db.commit()


def list_entries(
    db: Session,
    *,
    user_id: UUID,
    starts_from: datetime | None = None,
    starts_before: datetime | None = None,
    project_id: UUID | None = None,
) -> list[TimeEntry]:
    """Entries of one user, newest first."""
    stmt = select(TimeEntry).where(TimeEntry.user_id == user_id)

    if starts_from is not None:
        stmt = stmt.where(TimeEntry.started_at >= starts_from)
    if starts_before is not None:
        stmt = stmt.where(TimeEntry.started_at < starts_before)
    if project_id is not None:
        stmt = stmt.where(TimeEntry.project_id == project_id)

    return list(db.scalars(stmt.order_by(TimeEntry.started_at.desc())))
