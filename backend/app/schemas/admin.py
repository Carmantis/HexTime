"""Request and response models for the administrator's user list."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.admin import AddOutcome, UserStatus

#: One paste of a staff list; sending is one email per person.
MAX_PEOPLE_PER_ADD = 200


class AdminUserRead(BaseModel):
    id: UUID
    email: str
    display_name: str
    is_admin: bool
    is_active: bool
    status: UserStatus
    created_at: datetime


class PersonIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(default="", max_length=200)


class AddPeopleRequest(BaseModel):
    people: list[PersonIn] = Field(min_length=1, max_length=MAX_PEOPLE_PER_ADD)


class AddResultRead(BaseModel):
    email: str
    display_name: str
    outcome: AddOutcome
    user_id: UUID | None


class AddPeopleResponse(BaseModel):
    results: list[AddResultRead]


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None
