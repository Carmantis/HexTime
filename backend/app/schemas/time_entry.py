"""Request and response models for time entries.

``AwareDatetime`` rejects a timestamp without an offset at the edge of the
system, so a naive time becomes a clear 422 instead of reaching the database
layer and failing there.
"""

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.tag import TagRead


class TimeEntryRead(BaseModel):
    """A time entry as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    project_id: UUID | None
    task_id: UUID | None
    description: str | None
    started_at: datetime
    ended_at: datetime | None
    billable: bool
    rate_snapshot_cents: int | None
    currency: str
    #: Computed from the two timestamps, never stored. None while running.
    duration_seconds: int | None
    tags: list[TagRead] = Field(default_factory=list)


class TimeEntryCreate(BaseModel):
    """A manually entered time entry."""

    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    project_id: UUID | None = None
    task_id: UUID | None = None
    description: str | None = None
    #: None means "use the project's billable_default".
    billable: bool | None = None
    tag_ids: list[UUID] = Field(default_factory=list)


class TimeEntryUpdate(BaseModel):
    """A partial change.

    Every field is optional. The router passes on only the fields the request
    actually contained (``exclude_unset``), which is how "leave this alone" is
    told apart from "set this to null".
    """

    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    project_id: UUID | None = None
    task_id: UUID | None = None
    description: str | None = None
    billable: bool | None = None
    #: Replaces the whole set. Sending null or [] removes every tag.
    tag_ids: list[UUID] | None = None


class TimerStop(BaseModel):
    """Optional: when the user pressed Stop, if the request had to be retried."""

    at: AwareDatetime | None = None


class TimerStart(BaseModel):
    """What to start the timer on. Everything may be filled in later."""

    project_id: UUID | None = None
    task_id: UUID | None = None
    description: str | None = None
    billable: bool | None = None
    tag_ids: list[UUID] = Field(default_factory=list)
