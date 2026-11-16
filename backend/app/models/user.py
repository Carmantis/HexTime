"""Users and browser sessions."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UuidPk, utc_now


class User(UuidPk, Base):
    """A person. In local mode exactly one row exists, created on first start."""

    __tablename__ = "users"

    # Nullable: the local-mode default user has no email and never logs in.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(5), default="fi")
    theme: Mapped[str] = mapped_column(String(10), default="dark")
    is_active: Mapped[bool] = mapped_column(default=True)
    #: Organisation administrator (server mode): manages users, separate from
    #: the per-team roles. The first one is made with `create-admin`.
    is_admin: Mapped[bool] = mapped_column(default=False, server_default=false())
    email_verified_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class AuthSession(UuidPk, Base):
    """A logged-in browser session (server mode only).

    Named AuthSession so it never gets confused with SQLAlchemy's Session.
    Only the hash of the token is stored, so a database leak does not hand
    anybody a usable session.
    """

    __tablename__ = "sessions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    user_agent: Mapped[str | None] = mapped_column(String(400), default=None)


class LoginAttempt(UuidPk, Base):
    """A failed login, kept briefly to slow down password guessing.

    Stored in the database rather than in memory so the limit holds across
    restarts and across several server processes.
    """

    __tablename__ = "login_attempts"

    email: Mapped[str] = mapped_column(String(320), index=True)
    ip: Mapped[str] = mapped_column(String(45))
    attempted_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)


class TokenPurpose(StrEnum):
    """What a one-time link in an email is for."""

    #: Set your password for an account an administrator created (invitation).
    SETUP = "setup"
    #: Choose a new password after forgetting the old one.
    RESET = "reset"
    #: Confirm the address after signing up yourself.
    VERIFY = "verify"


class AccountToken(UuidPk, Base):
    """A single-use, expiring link sent by email. Only its hash is stored."""

    __tablename__ = "account_tokens"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[TokenPurpose] = mapped_column(
        Enum(
            TokenPurpose,
            native_enum=False,
            length=10,
            name="token_purpose",
            create_constraint=True,
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
