"""Teams, their members and pending invitations (server mode only)."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UuidPk, utc_now


class TeamRole(StrEnum):
    """What a member may do. Enforced in the backend, never only in the UI."""

    MEMBER = "member"
    #: Runs the team: members, roles, the team's projects and tags. Whoever
    #: creates a team is its first lead.
    LEAD = "lead"


#: native_enum=False stores a VARCHAR plus a CHECK constraint instead of a
#: PostgreSQL ENUM type, which would need its own migration on every change.
team_role_column = Enum(
    TeamRole,
    native_enum=False,
    length=10,
    name="team_role",
    # Without this the column is a bare VARCHAR that accepts any string:
    # create_constraint has defaulted to False since SQLAlchemy 1.4, so
    # native_enum=False alone validates nothing at all.
    create_constraint=True,
    # Store the lowercase values ("member"), not the member names ("MEMBER"),
    # which is what SQLAlchemy would persist by default.
    values_callable=lambda enum: [member.value for member in enum],
)


class Team(UuidPk, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class TeamMember(Base):
    """Join table. The composite primary key makes a duplicate pair impossible."""

    __tablename__ = "team_members"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[TeamRole] = mapped_column(team_role_column)
    joined_at: Mapped[datetime] = mapped_column(default=utc_now)


class TeamInvitation(Base):
    """A lead asked someone in the organisation to join; they have not answered.

    No token: the invited person is signed in when they answer, and the app
    asks them. Answering removes the row (and on yes, adds a TeamMember).
    """

    __tablename__ = "team_invitations"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    invited_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
