"""Request and response models for teams, members and invitations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import TeamRole
from app.services.admin import UserStatus


class TeamRead(BaseModel):
    id: UUID
    name: str
    #: The caller's own role; None for an organisation administrator outside it.
    role: TeamRole | None
    member_count: int
    #: May the caller run the team: its lead, or the administrator standing in.
    can_manage: bool
    #: False when no lead who can sign in is left.
    has_lead: bool
    created_at: datetime


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TeamUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberRead(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    role: TeamRole
    #: Whether they can sign in: an active, invited or disabled account.
    status: UserStatus
    joined_at: datetime


class MemberUpdate(BaseModel):
    role: TeamRole


class PersonRead(BaseModel):
    """Someone in the organisation, as the invite search shows them."""

    id: UUID
    email: str
    display_name: str


class InvitationCreate(BaseModel):
    user_id: UUID


class InvitationRead(BaseModel):
    """A person the team is waiting on."""

    user_id: UUID
    email: str
    display_name: str
    invited_at: datetime


class MyInvitationRead(BaseModel):
    """A team waiting on the caller's answer."""

    team_id: UUID
    team_name: str
    invited_by: str | None
    invited_at: datetime
