"""Dependencies shared by routers.

Routers declare what they need (a session, the current user) as parameters and
FastAPI supplies it. Nothing here contains business logic.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import AppMode, Settings, get_settings
from app.core.db import get_db
from app.core.errors import NotAuthenticatedError, NotFoundError, PermissionDeniedError
from app.models import User
from app.services import auth

#: Shown in the UI for the single user of the desktop build.
DEFAULT_LOCAL_USER_NAME = "Local user"

#: The cookie that carries the session token in server mode.
SESSION_COOKIE = "hextime_session"


def get_or_create_local_user(db: Session) -> User:
    """Return the desktop build's one user, creating it on first use.

    Every row in the database has an owner from day one, even in local mode,
    so that team support can be switched on later without a data migration.
    """
    user = db.scalars(select(User).order_by(User.created_at)).first()
    if user is not None:
        return user

    user = User(display_name=DEFAULT_LOCAL_USER_NAME)
    db.add(user)
    db.commit()
    return user


def get_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Who is making this request.

    Local mode has one user and no sign-in. Server mode reads the session
    cookie; without a valid one every route that needs a user answers 401.
    """
    if settings.app_mode is AppMode.LOCAL:
        return get_or_create_local_user(db)

    user = auth.user_for_session(
        db, request.cookies.get(SESSION_COOKIE), days=settings.session_days
    )
    if user is None:
        raise NotAuthenticatedError("sign in first")
    return user


def require_server_mode(settings: Annotated[Settings, Depends(get_settings)]) -> Settings:
    """For routes that only make sense with accounts. Local mode: 404."""
    if not settings.is_server:
        raise NotFoundError("not available in local mode")
    return settings


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
ServerSettings = Annotated[Settings, Depends(require_server_mode)]


def require_admin(user: CurrentUser, _settings: ServerSettings) -> User:
    """The organisation administrator, or 403. Server mode only (404 locally)."""
    if not user.is_admin:
        raise PermissionDeniedError("only an administrator can do this")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
