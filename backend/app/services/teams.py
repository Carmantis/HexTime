"""Teams, their members and invitations (server mode).

Decided 2026-10-08:

- The organisation administrator runs the server and adds people to the
  organisation. Anyone in it can create a team and becomes its lead.
- A lead invites people who are already in the organisation. Nobody is put
  in a team without saying yes: the app asks them "join team X?".
- A team has leads and members:

=========================================  ======  ====
Action                                     member  lead
=========================================  ======  ====
See the team, its members and invitations  yes     yes
Invite people, cancel an invitation        no      yes
Make a member a lead or back, remove       no      yes
Rename or delete the team                  no      yes
Leave the team                             yes     yes (not the last lead)
=========================================  ======  ====

The organisation administrator sees every team and its members, but acts as
a lead only in a team that has no lead left who can sign in (say the only
lead left the organisation). No role gives access to anyone else's time
entries (services/ownership.py).
"""

from contextlib import suppress
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import Email, Mailer
from app.core.errors import (
    AlreadyInvitedError,
    AlreadyMemberError,
    EmailFailedError,
    LastTeamLeadError,
    NotFoundError,
    PermissionDeniedError,
    TeamHasEntriesError,
    ValidationFailedError,
)
from app.core.i18n import resolve_locale, translator
from app.models import Project, Team, TeamInvitation, TeamMember, TeamRole, TimeEntry, User
from app.services import ownership


def _guard_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValidationFailedError("name must not be empty")
    return stripped


def has_active_lead(db: Session, team: Team) -> bool:
    """Is there a lead who can still sign in and look after the team?"""
    lead = db.scalar(
        select(TeamMember.user_id)
        .join(User, User.id == TeamMember.user_id)
        .where(
            TeamMember.team_id == team.id,
            TeamMember.role == TeamRole.LEAD,
            User.is_active.is_(True),
        )
        .limit(1)
    )
    return lead is not None


def acts_as_lead(db: Session, user: User, team: Team) -> bool:
    """A lead of the team, or the administrator standing in for a missing one."""
    if ownership.role_in_team(db, user, team.id) is TeamRole.LEAD:
        return True
    return user.is_admin and not has_active_lead(db, team)


def _require_lead(db: Session, user: User, team: Team) -> None:
    if not acts_as_lead(db, user, team):
        raise PermissionDeniedError("only a lead of the team can do this")


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TeamSummary:
    team: Team
    #: The user's own role; None for an organisation administrator outside it.
    role: TeamRole | None
    member_count: int
    #: Whether the user may run the team (as its lead, or standing in).
    can_manage: bool
    #: False when no lead who can sign in is left: the administrator steps in.
    has_lead: bool


def create_team(db: Session, *, user: User, name: str) -> Team:
    """A new team with its creator as the lead."""
    team = Team(name=_guard_name(name), created_by=user.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.LEAD))
    db.commit()
    return team


def list_teams(db: Session, *, user: User) -> list[TeamSummary]:
    """The user's teams; every team for the organisation administrator."""
    counts = (
        select(TeamMember.team_id, func.count().label("members"))
        .group_by(TeamMember.team_id)
        .subquery()
    )
    mine = (
        select(TeamMember.team_id, TeamMember.role).where(TeamMember.user_id == user.id).subquery()
    )
    stmt = (
        select(Team, mine.c.role, func.coalesce(counts.c.members, 0))
        .outerjoin(mine, mine.c.team_id == Team.id)
        .outerjoin(counts, counts.c.team_id == Team.id)
        .order_by(Team.name)
    )
    if not user.is_admin:
        stmt = stmt.where(mine.c.role.is_not(None))

    summaries = []
    for team, role, count in db.execute(stmt).all():
        has_lead = has_active_lead(db, team)
        own_role = TeamRole(role) if role else None
        can_manage = own_role is TeamRole.LEAD or (user.is_admin and not has_lead)
        summaries.append(TeamSummary(team, own_role, count, can_manage, has_lead))
    return summaries


def summary_of(db: Session, *, user: User, team_id: UUID) -> TeamSummary:
    return next(s for s in list_teams(db, user=user) if s.team.id == team_id)


def get_team(db: Session, team_id: UUID, user: User) -> Team:
    """A team the user is in (any team for the organisation administrator)."""
    team = db.get(Team, team_id)
    if team is None:
        raise NotFoundError("team not found")
    if not user.is_admin and ownership.role_in_team(db, user, team.id) is None:
        raise NotFoundError("team not found")
    return team


def rename_team(db: Session, *, actor: User, team: Team, name: str) -> Team:
    _require_lead(db, actor, team)
    team.name = _guard_name(name)
    db.commit()
    return team


def delete_team(db: Session, *, actor: User, team: Team) -> None:
    """Delete a team with its projects and tags.

    Refused while any time is booked on its projects: those hours belong to
    the people who worked them and must not disappear with the team.
    """
    _require_lead(db, actor, team)
    booked = db.scalar(
        select(TimeEntry.id)
        .join(Project, TimeEntry.project_id == Project.id)
        .where(Project.owner_team_id == team.id)
        .limit(1)
    )
    if booked is not None:
        raise TeamHasEntriesError("archive the team's projects instead")
    # The database cascades to members, invitations, projects with their
    # tasks, and tags.
    db.delete(team)
    db.commit()


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def list_members(db: Session, *, team: Team) -> list[tuple[User, TeamMember]]:
    stmt = (
        select(User, TeamMember)
        .join(TeamMember, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team.id)
        .order_by(User.display_name)
    )
    return [(user, member) for user, member in db.execute(stmt)]


def _membership(db: Session, team: Team, user_id: UUID) -> TeamMember:
    member = db.get(TeamMember, (team.id, user_id))
    if member is None:
        raise NotFoundError("member not found")
    return member


def _guard_last_lead(db: Session, team: Team, leaving: TeamMember) -> None:
    """A team must keep a lead who can sign in, while it has one at all."""
    if leaving.role is not TeamRole.LEAD:
        return
    other = db.scalar(
        select(TeamMember.user_id)
        .join(User, User.id == TeamMember.user_id)
        .where(
            TeamMember.team_id == team.id,
            TeamMember.role == TeamRole.LEAD,
            TeamMember.user_id != leaving.user_id,
            User.is_active.is_(True),
        )
        .limit(1)
    )
    if other is None:
        raise LastTeamLeadError("make someone else a lead of the team first")


def change_role(
    db: Session, *, actor: User, team: Team, user_id: UUID, role: TeamRole
) -> TeamMember:
    _require_lead(db, actor, team)
    member = _membership(db, team, user_id)
    if role is TeamRole.MEMBER:
        _guard_last_lead(db, team, member)
    member.role = role
    db.commit()
    return member


def remove_member(db: Session, *, actor: User, team: Team, user_id: UUID) -> None:
    """A lead removes anyone; anyone may leave by removing themselves.

    The person's time entries stay theirs.
    """
    if user_id != actor.id:
        _require_lead(db, actor, team)
    member = _membership(db, team, user_id)
    _guard_last_lead(db, team, member)
    db.delete(member)
    db.commit()


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


def find_people(db: Session, *, query: str, limit: int = 20) -> list[User]:
    """People in the organisation whose name or address matches, for inviting.

    Only accounts that can be used: not disabled, and with an address (local
    mode's address-less user is never one of them).
    """
    stmt = select(User).where(User.email.is_not(None), User.is_active.is_(True))
    words = query.strip().lower()
    if words:
        pattern = f"%{words}%"
        stmt = stmt.where(
            or_(func.lower(User.display_name).like(pattern), func.lower(User.email).like(pattern))
        )
    return list(db.scalars(stmt.order_by(User.display_name).limit(limit)))


def list_invitations(db: Session, *, team: Team) -> list[tuple[User, TeamInvitation]]:
    """Who has been asked to join and has not answered yet."""
    stmt = (
        select(User, TeamInvitation)
        .join(TeamInvitation, TeamInvitation.user_id == User.id)
        .where(TeamInvitation.team_id == team.id)
        .order_by(User.display_name)
    )
    return [(user, invitation) for user, invitation in db.execute(stmt)]


def invite(
    db: Session,
    *,
    actor: User,
    team: Team,
    user_id: UUID,
    settings: Settings | None = None,
    mailer: Mailer | None = None,
) -> tuple[User, TeamInvitation]:
    """Ask someone in the organisation to join. They answer in the app.

    With a mailer, they also get an email saying so, since the question only
    shows the next time they open HexTime. The invitation does not depend on
    it: a mail failure is logged and the invitation stands.
    """
    _require_lead(db, actor, team)
    person = db.get(User, user_id)
    if person is None or person.email is None or not person.is_active:
        raise NotFoundError("user not found")
    if db.get(TeamMember, (team.id, person.id)) is not None:
        raise AlreadyMemberError(f"{person.email} is in the team already")
    if db.get(TeamInvitation, (team.id, person.id)) is not None:
        raise AlreadyInvitedError(f"{person.email} has been invited already")

    invitation = TeamInvitation(team_id=team.id, user_id=person.id, invited_by=actor.id)
    db.add(invitation)
    db.commit()
    if settings is not None and mailer is not None:
        _email_invitation(mailer, settings, actor=actor, team=team, person=person)
    return person, invitation


def _email_invitation(
    mailer: Mailer, settings: Settings, *, actor: User, team: Team, person: User
) -> None:
    t = translator(resolve_locale(person.locale, settings.default_locale))
    body = t(
        "email.teamInvitation.body",
        inviter=actor.display_name,
        team=team.name,
        link=f"{(settings.public_base_url or '').rstrip('/')}/#/teams",
    )
    # A failure is already logged by the mailer; the question in the app
    # still comes, so the invitation does not depend on the email.
    with suppress(EmailFailedError):
        mailer.send(
            Email(
                to=person.email or "",
                subject=t("email.teamInvitation.subject", team=team.name),
                body=f"{t('email.greeting', name=person.display_name)}\n\n{body}\n\n"
                f"{t('email.signature')}",
            )
        )


def cancel_invitation(db: Session, *, actor: User, team: Team, user_id: UUID) -> None:
    _require_lead(db, actor, team)
    invitation = db.get(TeamInvitation, (team.id, user_id))
    if invitation is None:
        raise NotFoundError("invitation not found")
    db.delete(invitation)
    db.commit()


@dataclass(frozen=True)
class PendingInvitation:
    team: Team
    invited_by: User | None
    invitation: TeamInvitation


def my_invitations(db: Session, *, user: User) -> list[PendingInvitation]:
    """The invitations waiting for this user's answer, oldest first."""
    stmt = (
        select(TeamInvitation, Team)
        .join(Team, Team.id == TeamInvitation.team_id)
        .where(TeamInvitation.user_id == user.id)
        .order_by(TeamInvitation.created_at)
    )
    return [
        PendingInvitation(
            team, db.get(User, invitation.invited_by) if invitation.invited_by else None, invitation
        )
        for invitation, team in db.execute(stmt)
    ]


def answer_invitation(db: Session, *, user: User, team_id: UUID, accept: bool) -> None:
    """Yes joins the team as a member; no just removes the invitation."""
    invitation = db.get(TeamInvitation, (team_id, user.id))
    if invitation is None:
        raise NotFoundError("invitation not found")
    db.delete(invitation)
    if accept and db.get(TeamMember, (team_id, user.id)) is None:
        db.add(TeamMember(team_id=team_id, user_id=user.id, role=TeamRole.MEMBER))
    db.commit()
