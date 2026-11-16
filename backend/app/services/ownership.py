"""Who may see and change what.

Projects, tasks and tags belong to exactly one of a user or a team. Every
ownership decision goes through this module so there is a single place to
change, rather than the same check copied into every service.

The rules (fixed roles, decided 2026-10-06):

- A user's own rows are theirs alone.
- A team's rows are visible to every member of that team; changing them
  takes a lead of the team.
- Time entries are their owner's alone. Nobody else sees or changes them,
  whatever their role (decided 2026-10-08): a team sees only the total hours
  each member booked on the team's projects, through the team report.

The organisation administrator (``users.is_admin``) manages teams but has no
access to anyone's hours.
"""

from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, PermissionDeniedError
from app.models import TeamMember, TeamRole, User

#: The roles that may change a team's projects and tags.
MANAGERS = (TeamRole.LEAD,)


class Owned(Protocol):
    """Any row carrying the two owner columns."""

    owner_user_id: UUID | None
    owner_team_id: UUID | None


def team_ids_of(user: User, roles: tuple[TeamRole, ...] | None = None) -> Select[tuple[UUID]]:
    """The teams this user is in (with one of `roles`, if given), as a subquery."""
    stmt = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    if roles is not None:
        stmt = stmt.where(TeamMember.role.in_(roles))
    return stmt


def role_in_team(db: Session, user: User, team_id: UUID) -> TeamRole | None:
    """The user's own role in the team, or None if they are not in it."""
    return db.scalar(
        select(TeamMember.role).where(TeamMember.team_id == team_id, TeamMember.user_id == user.id)
    )


def visible_to(model: Any, user: User) -> ColumnElement[bool]:
    """A WHERE clause selecting the rows this user may see."""
    return or_(model.owner_user_id == user.id, model.owner_team_id.in_(team_ids_of(user)))


def is_visible_to(db: Session, row: Owned, user: User) -> bool:
    if row.owner_team_id is not None:
        return role_in_team(db, user, row.owner_team_id) is not None
    return row.owner_user_id == user.id


def require_visible(db: Session, row: Owned | None, user: User, what: str) -> Any:
    """Return the row, or raise NotFound if the user may not see it.

    Deliberately "not found" rather than "forbidden": answering differently
    for a row that exists but belongs to someone else would let a caller probe
    which ids are real.
    """
    if row is None or not is_visible_to(db, row, user):
        raise NotFoundError(f"{what} not found")
    return row


def require_changeable(db: Session, row: Owned | None, user: User, what: str) -> Any:
    """Return the row if the user may change it.

    Not visible: NotFound, as above. Visible but the team's, and the user is
    a plain member: PermissionDenied, which reveals nothing they cannot see.
    """
    require_visible(db, row, user, what)
    assert row is not None
    if row.owner_team_id is not None and role_in_team(db, user, row.owner_team_id) not in MANAGERS:
        raise PermissionDeniedError(f"only a lead of the team can change this {what}")
    return row


def require_team_manager(db: Session, user: User, team_id: UUID) -> None:
    """For creating a project or tag in a team: a lead of it."""
    role = role_in_team(db, user, team_id)
    if role is None:
        raise NotFoundError("team not found")
    if role not in MANAGERS:
        raise PermissionDeniedError("only a lead of the team can do this")
