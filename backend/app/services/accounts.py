"""Accounts through one-time email links (server mode).

Nobody ever receives a password by email. Instead:

* An administrator adds a person: the account is created without a password
  and a SETUP link lets them choose one. Opening the link also proves the
  address, so no separate confirmation is needed.
* A forgotten password: a RESET link, short-lived, answered the same way
  whether or not the address has an account.
* Signing up yourself (only if the server allows it): like being added by
  an administrator, the account starts without a password and a SETUP link
  lets the owner of the address choose one. Taking the password at sign-up
  would let anyone pre-register someone else's address with a password of
  their own, which would start to work the moment the real owner clicked
  "confirm". (VERIFY links from before this change still work until they
  expire.)

Links carry the token after "#" in the URL. The part after "#" never leaves
the browser, so the token does not end up in server or proxy logs.
"""

import re
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import Email, Mailer
from app.core.errors import (
    EmailDomainNotAllowedError,
    InvalidTokenError,
    RegistrationClosedError,
    UserExistsError,
)
from app.core.i18n import resolve_locale, translator
from app.core.security import check_password_rules, hash_password, hash_token, new_token
from app.models import AccountToken, TokenPurpose, User, utc_now
from app.services.auth import end_all_sessions, find_user_by_email, normalize_email

LIFETIMES = {
    TokenPurpose.SETUP: timedelta(days=7),
    TokenPurpose.RESET: timedelta(hours=2),
    TokenPurpose.VERIFY: timedelta(hours=24),
}

#: Where each link opens in the frontend (hash routes).
LINK_PATHS = {
    TokenPurpose.SETUP: "set-password",
    TokenPurpose.RESET: "set-password",
    TokenPurpose.VERIFY: "verify-email",
}

#: A second "forgot password" within this time sends nothing, so nobody can
#: flood someone's inbox through the form.
RESEND_PAUSE = timedelta(minutes=1)

#: How long a used link's row is kept before issue_token() deletes it.
USED_TOKEN_KEPT = timedelta(days=1)


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def issue_token(db: Session, user: User, purpose: TokenPurpose) -> str:
    """A fresh link token. Earlier unused ones for the same purpose stop working.

    Also clears out links nobody can use any more: expired ones, and ones used
    over a day ago. (Not at once: the resend pause looks at the newest links.)
    """
    now = utc_now()
    db.execute(
        delete(AccountToken).where(
            (AccountToken.expires_at <= now) | (AccountToken.used_at <= now - USED_TOKEN_KEPT)
        )
    )
    db.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    token = new_token()
    db.add(
        AccountToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=now + LIFETIMES[purpose],
        )
    )
    return token


def _valid_token(db: Session, token: str, purposes: set[TokenPurpose]) -> AccountToken:
    """The stored token, if it exists, is unused, unexpired and for this purpose.

    One error for every way a link can be wrong: the page only needs to say
    "ask for a new link".
    """
    stored = db.scalars(
        select(AccountToken).where(AccountToken.token_hash == hash_token(token))
    ).first()
    if (
        stored is None
        or stored.purpose not in purposes
        or stored.used_at is not None
        or stored.expires_at <= utc_now()
    ):
        raise InvalidTokenError("this link is not valid any more")
    return stored


def inspect_token(db: Session, token: str) -> tuple[User, TokenPurpose]:
    """Whose link this is and what for, without using it up.

    Lets the page greet the person by name, or say at once that the link has
    expired, before they type a password.
    """
    stored = _valid_token(db, token, set(TokenPurpose))
    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError("this link is not valid any more")
    return user, stored.purpose


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def _link(settings: Settings, purpose: TokenPurpose, token: str) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return f"{base}/#/{LINK_PATHS[purpose]}?token={token}"


def send_link_email(
    mailer: Mailer,
    settings: Settings,
    user: User,
    purpose: TokenPurpose,
    token: str,
    *,
    text: str | None = None,
) -> None:
    """Email `user` the link for `token`, in the user's own language.

    `text` picks the wording (`email.<text>.*`) when the purpose's own does
    not fit, e.g. a SETUP link the person asked for themselves.
    """
    t = translator(resolve_locale(user.locale, settings.default_locale))
    text = text or str(purpose)
    lifetime = LIFETIMES[purpose]
    body = t(
        f"email.{text}.body",
        link=_link(settings, purpose, token),
        days=lifetime.days,
        hours=int(lifetime.total_seconds() // 3600),
    )
    greeting = t("email.greeting", name=user.display_name)
    mailer.send(
        Email(
            to=user.email or "",
            subject=t(f"email.{text}.subject"),
            body=f"{greeting}\n\n{body}\n\n{t('email.signature')}",
        )
    )


# ---------------------------------------------------------------------------
# Flows
# ---------------------------------------------------------------------------


#: One plain address: the characters RFC 5322 allows unquoted in the local
#: part, and a domain of letters, digits and hyphens. Anything an email header
#: would read as more than one address (a comma, "Name <x@y>", quotes,
#: another @) does not match, so a link can only ever go to that one address.
PLAIN_ADDRESS = re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]+@[a-z0-9-]+(\.[a-z0-9-]+)+")


def check_email_domain(email: str, settings: Settings) -> str:
    """The normalised address, if it is one address in the organisation's domain.

    Checking only the text after the last "@" is not enough: "me@evil.example,
    anna@example.org" ends in the right domain, yet an email to it reaches
    both addresses, and with it the link that confirms the account.
    """
    email = normalize_email(email)
    allowed = (settings.allowed_email_domain or "").lower().lstrip("@")
    domain = email.rpartition("@")[2]
    if not PLAIN_ADDRESS.fullmatch(email) or domain != allowed:
        raise EmailDomainNotAllowedError(f"only addresses @{allowed} can have an account")
    return email


def invite_user(
    db: Session, *, email: str, display_name: str, settings: Settings, mailer: Mailer
) -> User:
    """Create an account without a password and send its SETUP link.

    Adding someone who was invited but never set a password sends a fresh
    link (the old one stops working). Someone who already has an active
    account is an error the administrator should see.
    """
    email = check_email_domain(email, settings)
    user = find_user_by_email(db, email)
    if user is not None and user.password_hash is not None:
        raise UserExistsError(f"{email} already has an account")
    if user is None:
        user = User(email=email, locale=settings.default_locale, display_name="")
        db.add(user)
    user.display_name = display_name.strip() or user.display_name or email.split("@")[0]
    user.is_active = True
    db.flush()

    token = issue_token(db, user, TokenPurpose.SETUP)
    # Committed before sending: if the mail server fails, the person is still
    # on the list and the administrator can send the link again.
    db.commit()
    send_link_email(mailer, settings, user, TokenPurpose.SETUP, token)
    return user


def set_password(db: Session, *, token: str, password: str) -> User:
    """Use a SETUP or RESET link: store the new password, sign out elsewhere."""
    check_password_rules(password)
    stored = _valid_token(db, token, {TokenPurpose.SETUP, TokenPurpose.RESET})
    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError("this link is not valid any more")

    user.password_hash = hash_password(password)
    # The link arrived at this address, which proves it belongs to them.
    user.email_verified_at = user.email_verified_at or utc_now()
    stored.used_at = utc_now()
    db.commit()
    # A reset is often because someone else might know the old password.
    end_all_sessions(db, user)
    return user


def _recently_sent(db: Session, user: User, purpose: TokenPurpose) -> bool:
    latest = db.scalars(
        select(AccountToken.created_at)
        .where(AccountToken.user_id == user.id, AccountToken.purpose == purpose)
        .order_by(AccountToken.created_at.desc())
    ).first()
    return latest is not None and latest > utc_now() - RESEND_PAUSE


def request_password_reset(db: Session, *, email: str, settings: Settings, mailer: Mailer) -> None:
    """Send a RESET link if the address has an account. Silent otherwise.

    The caller answers the same either way, so the form cannot be used to
    find out who has an account. Someone who never finished setting up gets
    their SETUP link again instead, which is what they actually need.
    """
    user = find_user_by_email(db, email)
    if user is None or not user.is_active:
        return
    purpose = TokenPurpose.RESET if user.password_hash else TokenPurpose.SETUP
    if _recently_sent(db, user, purpose):
        return
    token = issue_token(db, user, purpose)
    db.commit()
    send_link_email(mailer, settings, user, purpose, token)


def register(
    db: Session,
    *,
    email: str,
    display_name: str,
    settings: Settings,
    mailer: Mailer,
) -> None:
    """Sign up yourself, if the server allows it.

    The account starts without a password; the email brings a link for
    choosing one, so only whoever reads that inbox can ever sign in. For an
    address that already has an account nothing new is created; its owner
    gets a password-reset link instead, and the answer to the caller is the
    same as for a new account.
    """
    if not settings.allow_self_registration:
        raise RegistrationClosedError("ask an administrator to add you")
    email = check_email_domain(email, settings)

    existing = find_user_by_email(db, email)
    if existing is not None:
        request_password_reset(db, email=email, settings=settings, mailer=mailer)
        return

    user = User(
        email=email,
        display_name=display_name.strip() or email.split("@")[0],
        locale=settings.default_locale,
    )
    db.add(user)
    db.flush()
    token = issue_token(db, user, TokenPurpose.SETUP)
    db.commit()
    send_link_email(mailer, settings, user, TokenPurpose.SETUP, token, text="signup")


def verify_email(db: Session, *, token: str) -> User:
    stored = _valid_token(db, token, {TokenPurpose.VERIFY})
    user = db.get(User, stored.user_id)
    if user is None:
        raise InvalidTokenError("this link is not valid any more")
    user.email_verified_at = user.email_verified_at or utc_now()
    stored.used_at = utc_now()
    db.commit()
    return user
