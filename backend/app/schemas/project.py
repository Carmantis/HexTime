"""Request and response models for projects and tasks.

Format and range checks live here, at the edge. Business rules (ownership,
archiving) live in the service.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import DEFAULT_PROJECT_COLOR

#: A six-digit hex colour, the only form the theme's tokens understand.
HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    #: Set when the project is a team's; None for the user's own.
    owner_team_id: UUID | None
    name: str
    color: str
    client_name: str | None
    billable_default: bool
    hourly_rate_cents: int | None
    currency: str
    archived_at: datetime | None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    color: str = Field(default=DEFAULT_PROJECT_COLOR, pattern=HEX_COLOR)
    client_name: str | None = Field(default=None, max_length=200)
    billable_default: bool = False
    #: Integer cents, never a float, and never negative.
    hourly_rate_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    #: Make it the team's project instead of one's own. Leads only.
    team_id: UUID | None = None


class ProjectUpdate(BaseModel):
    """Every field optional; only the ones present are applied."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    color: str | None = Field(default=None, pattern=HEX_COLOR)
    client_name: str | None = Field(default=None, max_length=200)
    billable_default: bool | None = None
    hourly_rate_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    archived_at: datetime | None


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
