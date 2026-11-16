"""Projects, tasks ("nimikkeet") and tags.

All three are owned by exactly one of a user or a team, from day one, so that
team support can be switched on later without a data migration. All three are
archived rather than deleted, so old time entries keep their context.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UuidPk

#: "exactly one of the two is set" — (a IS NULL) <> (b IS NULL) is true only
#: when the two nullability states differ. Works on SQLite and PostgreSQL.
_EXACTLY_ONE_OWNER = "(owner_user_id IS NULL) <> (owner_team_id IS NULL)"

#: HexCalendar's accent colour, so a new project looks native in both themes.
DEFAULT_PROJECT_COLOR = "#4A90D9"


class Project(UuidPk, Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint(_EXACTLY_ONE_OWNER, name="ck_projects_exactly_one_owner"),)

    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), default=None, index=True
    )
    owner_team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(7), default=DEFAULT_PROJECT_COLOR)
    client_name: Mapped[str | None] = mapped_column(String(200), default=None)
    billable_default: Mapped[bool] = mapped_column(default=False)
    # Money is always integer cents. Never a float.
    hourly_rate_cents: Mapped[int | None] = mapped_column(default=None)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    archived_at: Mapped[datetime | None] = mapped_column(default=None)


class Task(UuidPk, Base):
    """A type of work inside a project, e.g. Design, Development, Meeting."""

    __tablename__ = "tasks"

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    archived_at: Mapped[datetime | None] = mapped_column(default=None)


class Tag(UuidPk, Base):
    __tablename__ = "tags"
    __table_args__ = (CheckConstraint(_EXACTLY_ONE_OWNER, name="ck_tags_exactly_one_owner"),)

    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), default=None, index=True
    )
    owner_team_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(7), default=DEFAULT_PROJECT_COLOR)
    archived_at: Mapped[datetime | None] = mapped_column(default=None)
