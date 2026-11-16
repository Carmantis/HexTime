"""Accounts: administrators (server mode) and everyone's own profile."""

from sqlalchemy.orm import Session

from app.core.errors import ValidationFailedError
from app.core.security import hash_password
from app.models import User, utc_now
from app.services.auth import find_user_by_email, normalize_email


def make_admin(db: Session, *, email: str, display_name: str, password: str) -> User:
    """Create an organisation administrator, or promote an existing account.

    Used by `create-admin` on a fresh server, and to recover when every
    administrator has lost their password: running it again for an existing
    address sets a new password and makes sure the account is active.
    """
    email = normalize_email(email)
    if "@" not in email:
        raise ValidationFailedError("that is not an email address")

    user = find_user_by_email(db, email)
    if user is None:
        user = User(email=email, display_name=display_name.strip() or email)
        db.add(user)
    user.password_hash = hash_password(password)
    user.is_admin = True
    user.is_active = True
    # Whoever runs this has shell access to the server; that is proof enough.
    user.email_verified_at = user.email_verified_at or utc_now()
    db.commit()
    return user


def update_profile(
    db: Session,
    *,
    user: User,
    display_name: str | None = None,
    locale: str | None = None,
    theme: str | None = None,
) -> User:
    """Change the user's own name, language or theme."""
    if display_name is not None:
        name = display_name.strip()
        if not name:
            raise ValidationFailedError("the name cannot be empty")
        user.display_name = name
    if locale is not None:
        user.locale = locale
    if theme is not None:
        user.theme = theme
    db.commit()
    return user
