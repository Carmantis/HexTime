"""Team routes. Server mode only: local mode has one user and no teams.

Thin routing; every permission check is in app/services/teams.py.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import CurrentUser, DbSession, ServerSettings, require_server_mode
from app.core.email import MailerDep
from app.models import TeamInvitation, TeamMember, User
from app.schemas.team import (
    InvitationCreate,
    InvitationRead,
    MemberRead,
    MemberUpdate,
    MyInvitationRead,
    PersonRead,
    TeamCreate,
    TeamRead,
    TeamUpdate,
)
from app.services import admin, teams

_server_only = [Depends(require_server_mode)]
router = APIRouter(prefix="/teams", tags=["teams"], dependencies=_server_only)
invitations_router = APIRouter(prefix="/invitations", tags=["teams"], dependencies=_server_only)
people_router = APIRouter(prefix="/people", tags=["teams"], dependencies=_server_only)


def _team(summary: teams.TeamSummary) -> TeamRead:
    return TeamRead(
        id=summary.team.id,
        name=summary.team.name,
        role=summary.role,
        member_count=summary.member_count,
        can_manage=summary.can_manage,
        has_lead=summary.has_lead,
        created_at=summary.team.created_at,
    )


def _member(user: User, member: TeamMember) -> MemberRead:
    return MemberRead(
        user_id=user.id,
        email=user.email or "",
        display_name=user.display_name,
        role=member.role,
        status=admin.status_of(user),
        joined_at=member.joined_at,
    )


def _invitation(user: User, invitation: TeamInvitation) -> InvitationRead:
    return InvitationRead(
        user_id=user.id,
        email=user.email or "",
        display_name=user.display_name,
        invited_at=invitation.created_at,
    )


# ---------------------------------------------------------------------------
# Teams and members
# ---------------------------------------------------------------------------


@router.get("", response_model=list[TeamRead])
def list_teams(user: CurrentUser, db: DbSession) -> list[TeamRead]:
    """The caller's teams; every team for the organisation administrator."""
    return [_team(summary) for summary in teams.list_teams(db, user=user)]


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
def create_team(payload: TeamCreate, user: CurrentUser, db: DbSession) -> TeamRead:
    """A new team, with the caller as its lead."""
    team = teams.create_team(db, user=user, name=payload.name)
    return _team(teams.summary_of(db, user=user, team_id=team.id))


@router.patch("/{team_id}", response_model=TeamRead)
def rename_team(team_id: UUID, payload: TeamUpdate, user: CurrentUser, db: DbSession) -> TeamRead:
    team = teams.get_team(db, team_id, user)
    teams.rename_team(db, actor=user, team=team, name=payload.name)
    return _team(teams.summary_of(db, user=user, team_id=team.id))


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(team_id: UUID, user: CurrentUser, db: DbSession) -> None:
    teams.delete_team(db, actor=user, team=teams.get_team(db, team_id, user))


@router.get("/{team_id}/members", response_model=list[MemberRead])
def list_members(team_id: UUID, user: CurrentUser, db: DbSession) -> list[MemberRead]:
    team = teams.get_team(db, team_id, user)
    return [_member(u, m) for u, m in teams.list_members(db, team=team)]


@router.patch("/{team_id}/members/{user_id}", response_model=MemberRead)
def change_role(
    team_id: UUID, user_id: UUID, payload: MemberUpdate, user: CurrentUser, db: DbSession
) -> MemberRead:
    team = teams.get_team(db, team_id, user)
    member = teams.change_role(db, actor=user, team=team, user_id=user_id, role=payload.role)
    person = db.get(User, member.user_id)
    assert person is not None
    return _member(person, member)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(team_id: UUID, user_id: UUID, user: CurrentUser, db: DbSession) -> None:
    """Remove someone (a lead), or leave the team yourself."""
    teams.remove_member(db, actor=user, team=teams.get_team(db, team_id, user), user_id=user_id)


# ---------------------------------------------------------------------------
# Inviting (the lead's side)
# ---------------------------------------------------------------------------


@router.get("/{team_id}/invitations", response_model=list[InvitationRead])
def list_invitations(team_id: UUID, user: CurrentUser, db: DbSession) -> list[InvitationRead]:
    team = teams.get_team(db, team_id, user)
    return [_invitation(u, i) for u, i in teams.list_invitations(db, team=team)]


@router.post(
    "/{team_id}/invitations", response_model=InvitationRead, status_code=status.HTTP_201_CREATED
)
def invite(
    team_id: UUID,
    payload: InvitationCreate,
    user: CurrentUser,
    db: DbSession,
    settings: ServerSettings,
    mailer: MailerDep,
) -> InvitationRead:
    """Ask someone in the organisation to join; they answer in the app, and
    get an email saying so."""
    team = teams.get_team(db, team_id, user)
    person, invitation = teams.invite(
        db, actor=user, team=team, user_id=payload.user_id, settings=settings, mailer=mailer
    )
    return _invitation(person, invitation)


@router.delete("/{team_id}/invitations/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invitation(team_id: UUID, user_id: UUID, user: CurrentUser, db: DbSession) -> None:
    team = teams.get_team(db, team_id, user)
    teams.cancel_invitation(db, actor=user, team=team, user_id=user_id)


@people_router.get("", response_model=list[PersonRead])
def find_people(
    _user: CurrentUser, db: DbSession, q: Annotated[str, Query(max_length=100)] = ""
) -> list[PersonRead]:
    """People in the organisation by name or address, to invite to a team."""
    return [
        PersonRead(id=p.id, email=p.email or "", display_name=p.display_name)
        for p in teams.find_people(db, query=q)
    ]


# ---------------------------------------------------------------------------
# Answering (the invited person's side)
# ---------------------------------------------------------------------------


@invitations_router.get("", response_model=list[MyInvitationRead])
def my_invitations(user: CurrentUser, db: DbSession) -> list[MyInvitationRead]:
    """Teams waiting for the caller's answer. The app asks about each."""
    return [
        MyInvitationRead(
            team_id=pending.team.id,
            team_name=pending.team.name,
            invited_by=pending.invited_by.display_name if pending.invited_by else None,
            invited_at=pending.invitation.created_at,
        )
        for pending in teams.my_invitations(db, user=user)
    ]


@invitations_router.post("/{team_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
def accept(team_id: UUID, user: CurrentUser, db: DbSession) -> None:
    teams.answer_invitation(db, user=user, team_id=team_id, accept=True)


@invitations_router.post("/{team_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline(team_id: UUID, user: CurrentUser, db: DbSession) -> None:
    teams.answer_invitation(db, user=user, team_id=team_id, accept=False)
