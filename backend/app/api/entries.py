"""Time entry routes.

Thin routing only. The overlap rule, the rate snapshot and the audit log all
live in app/services/entries.py.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import AwareDatetime

from app.core.deps import CurrentUser, DbSession
from app.schemas.time_entry import TimeEntryCreate, TimeEntryRead, TimeEntryUpdate
from app.services import entries

router = APIRouter(prefix="/entries", tags=["entries"])

#: "from" and "to" are the natural query names but "from" is a Python keyword,
#: so the parameters are aliased.
FromQuery = Annotated[AwareDatetime | None, Query(alias="from")]
ToQuery = Annotated[AwareDatetime | None, Query(alias="to")]


@router.get("", response_model=list[TimeEntryRead])
def list_time_entries(
    user: CurrentUser,
    db: DbSession,
    starts_from: FromQuery = None,
    starts_before: ToQuery = None,
    project_id: UUID | None = None,
) -> object:
    """Entries of the signed-in user, newest first. Only ever one's own: a
    team sees members' hours as totals in the team report, never entries."""
    return entries.list_entries(
        db,
        user_id=user.id,
        starts_from=starts_from,
        starts_before=starts_before,
        project_id=project_id,
    )


@router.post("", response_model=TimeEntryRead, status_code=status.HTTP_201_CREATED)
def create_time_entry(payload: TimeEntryCreate, user: CurrentUser, db: DbSession) -> object:
    return entries.create_entry(
        db,
        user=user,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        project_id=payload.project_id,
        task_id=payload.task_id,
        description=payload.description,
        billable=payload.billable,
        tag_ids=payload.tag_ids,
    )


@router.get("/{entry_id}", response_model=TimeEntryRead)
def read_time_entry(entry_id: UUID, user: CurrentUser, db: DbSession) -> object:
    return entries.get_entry(db, entry_id, user)


@router.patch("/{entry_id}", response_model=TimeEntryRead)
def update_time_entry(
    entry_id: UUID, payload: TimeEntryUpdate, user: CurrentUser, db: DbSession
) -> object:
    """Apply only the fields the request actually contained.

    ``exclude_unset`` is what makes ``{"description": null}`` clear the
    description while an absent key leaves it untouched.
    """
    entry = entries.get_entry(db, entry_id, user)
    changes = payload.model_dump(exclude_unset=True)
    return entries.update_entry(db, entry=entry, actor=user, **changes)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_entry(entry_id: UUID, user: CurrentUser, db: DbSession) -> None:
    entry = entries.get_entry(db, entry_id, user)
    entries.delete_entry(db, entry=entry, actor=user)
