"""The organisation administrator's tools (server mode): the list of people,
adding many at once, sending a fresh sign-in link, disabling an account.

Nothing is ever deleted. A disabled account cannot sign in, but its time
entries stay in the reports where they belong.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import Mailer
from app.core.errors import (
    CannotChangeSelfError,
    EmailDomainNotAllowedError,
    EmailFailedError,
    NotFoundError,
    UserExistsError,
    ValidationFailedError,
)
from app.models import TokenPurpose, User
from app.services.accounts import invite_user, issue_token, send_link_email
from app.services.auth import end_all_sessions, find_user_by_email, normalize_email


class UserStatus(StrEnum):
    """Where an account is, from the administrator's point of view."""

    ACTIVE = "active"
    #: Added, but has not set a password from the link yet.
    INVITED = "invited"
    #: Signed up themselves and has not confirmed the address yet.
    UNVERIFIED = "unverified"
    DISABLED = "disabled"


def status_of(user: User) -> UserStatus:
    if not user.is_active:
        return UserStatus.DISABLED
    if user.password_hash is None:
        return UserStatus.INVITED
    if user.email_verified_at is None:
        return UserStatus.UNVERIFIED
    return UserStatus.ACTIVE


def list_users(db: Session) -> list[User]:
    """Everyone with an address. (Local mode's address-less user is not one.)"""
    return list(db.scalars(select(User).where(User.email.is_not(None)).order_by(User.display_name)))


def get_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None or user.email is None:
        raise NotFoundError("user not found")
    return user


class AddOutcome(StrEnum):
    INVITED = "invited"
    #: Was already on the list without a password; a fresh link went out.
    RESENT = "resent"
    EXISTS = "exists"
    INVALID_DOMAIN = "invalid_domain"
    #: Listed twice in the same batch; added once.
    DUPLICATE = "duplicate"
    #: The account was created, but the email did not go out. Resend later.
    EMAIL_FAILED = "email_failed"


@dataclass(frozen=True)
class Person:
    email: str
    display_name: str


@dataclass(frozen=True)
class AddResult:
    email: str
    display_name: str
    outcome: AddOutcome
    user_id: UUID | None = None


def add_people(
    db: Session,
    *,
    people: list[Person],
    settings: Settings,
    mailer: Mailer,
) -> list[AddResult]:
    """Invite everyone on the list, one result per row, in the same order.

    One bad row never stops the rest: the administrator gets a report of what
    happened to each person and can fix and resend the few that failed.
    """
    seen: set[str] = set()
    results: list[AddResult] = []
    for person in people:
        email = normalize_email(person.email)
        name = person.display_name.strip()
        if email in seen:
            results.append(AddResult(email, name, AddOutcome.DUPLICATE))
            continue
        seen.add(email)

        existed = find_user_by_email(db, email) is not None
        try:
            user = invite_user(db, email=email, display_name=name, settings=settings, mailer=mailer)
        except EmailDomainNotAllowedError:
            results.append(AddResult(email, name, AddOutcome.INVALID_DOMAIN))
        except UserExistsError:
            existing = find_user_by_email(db, email)
            results.append(
                AddResult(email, name, AddOutcome.EXISTS, existing.id if existing else None)
            )
        except EmailFailedError:
            # invite_user commits before sending, so the account is there.
            user = find_user_by_email(db, email)
            results.append(
                AddResult(email, name, AddOutcome.EMAIL_FAILED, user.id if user else None)
            )
        else:
            outcome = AddOutcome.RESENT if existed else AddOutcome.INVITED
            results.append(AddResult(email, user.display_name, outcome, user.id))
    return results


def send_sign_in_link(db: Session, *, user: User, settings: Settings, mailer: Mailer) -> None:
    """Email a fresh link: to set a password if there is none yet, else to reset it.

    For the person who lost their invitation or cannot get in. No pause
    between sends here, unlike the public form: an administrator asked.
    """
    if not user.is_active:
        raise ValidationFailedError("enable the account before sending a link")
    purpose = TokenPurpose.SETUP if user.password_hash is None else TokenPurpose.RESET
    token = issue_token(db, user, purpose)
    db.commit()
    send_link_email(mailer, settings, user, purpose, token)


def update_user(
    db: Session,
    *,
    actor: User,
    user: User,
    is_active: bool | None = None,
    is_admin: bool | None = None,
) -> User:
    """Disable or enable an account, or grant or remove administrator rights.

    Never on oneself: an organisation could otherwise lock itself out of its
    own administration. Since the acting administrator stays, there is always
    at least one.
    """
    if user.id == actor.id and (is_active is False or is_admin is False):
        raise CannotChangeSelfError("ask another administrator to do this")
    if is_active is not None:
        user.is_active = is_active
    if is_admin is not None:
        user.is_admin = is_admin
    db.commit()
    if is_active is False:
        # Out at once, not when their session would have expired.
        end_all_sessions(db, user)
    return user
