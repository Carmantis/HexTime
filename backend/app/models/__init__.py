"""SQLAlchemy models.

Every model is imported here so that ``Base.metadata`` is complete when Alembic
autogenerates a migration. A model that is not imported here is invisible to
Alembic and will silently never get a table.
"""

from app.models.audit import AuditLog
from app.models.base import Base, UtcDateTime, UuidPk, utc_now
from app.models.project import DEFAULT_PROJECT_COLOR, Project, Tag, Task
from app.models.team import Team, TeamInvitation, TeamMember, TeamRole
from app.models.time_entry import TimeEntry, time_entry_tags
from app.models.user import AccountToken, AuthSession, LoginAttempt, TokenPurpose, User

__all__ = [
    "DEFAULT_PROJECT_COLOR",
    "AccountToken",
    "AuditLog",
    "AuthSession",
    "Base",
    "LoginAttempt",
    "Project",
    "Tag",
    "Task",
    "Team",
    "TeamInvitation",
    "TeamMember",
    "TeamRole",
    "TimeEntry",
    "TokenPurpose",
    "User",
    "UtcDateTime",
    "UuidPk",
    "time_entry_tags",
    "utc_now",
]
