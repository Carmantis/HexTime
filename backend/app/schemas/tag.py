"""Request and response models for tags."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import DEFAULT_PROJECT_COLOR
from app.schemas.project import HEX_COLOR


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    #: Set when the tag is a team's; None for the user's own.
    owner_team_id: UUID | None
    name: str
    color: str
    archived_at: datetime | None


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(default=DEFAULT_PROJECT_COLOR, pattern=HEX_COLOR)
    #: Make it the team's tag instead of one's own. Leads only.
    team_id: UUID | None = None


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=HEX_COLOR)
