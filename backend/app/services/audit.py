"""Writing the audit log.

Every change to a time entry is recorded with the row as it was and as it
became, so the history of booked hours can always be traced.

These functions add to the session but never commit: the caller owns the
transaction, so the log and the change it describes are written together or
not at all.
"""

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog, TimeEntry

ENTITY_TIME_ENTRY = "time_entry"

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"


def entry_snapshot(entry: TimeEntry) -> dict[str, Any]:
    """The fields of a time entry worth remembering.

    Times are ISO 8601 UTC strings so the log stays readable and comparable
    long after the row itself is gone.
    """
    return {
        "user_id": str(entry.user_id),
        "project_id": str(entry.project_id) if entry.project_id else None,
        "task_id": str(entry.task_id) if entry.task_id else None,
        "description": entry.description,
        "started_at": entry.started_at.isoformat(),
        "ended_at": entry.ended_at.isoformat() if entry.ended_at else None,
        "billable": entry.billable,
        "rate_snapshot_cents": entry.rate_snapshot_cents,
        "currency": entry.currency,
        # Sorted so the same set of tags always serialises identically and a
        # diff of before/after never shows a change that did not happen.
        "tag_ids": sorted(str(tag.id) for tag in entry.tags),
    }


def record(
    db: Session,
    *,
    actor_user_id: UUID | None,
    entity_type: str,
    entity_id: UUID,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """Add one audit row to the session."""
    log = AuditLog(
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_json=json.dumps(before, sort_keys=True) if before is not None else None,
        after_json=json.dumps(after, sort_keys=True) if after is not None else None,
    )
    db.add(log)
    return log
