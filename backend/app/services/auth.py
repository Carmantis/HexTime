"""Signing in and out (server mode).

A session is a random token in an httpOnly cookie; the database keeps only its
hash. A session lasts `session_days` from its last use, so people who use the
app daily stay signed in and an abandoned session runs out on its own.

Failed logins are counted per email address and network address. After
MAX_FAILURES in FAILURE_WINDOW the pair is refused until the window passes.
A network address is also refused after MAX_FAILURES_PER_IP failures on any
addresses together, so nobody can try one likely password on every account.
The limit is generous because a whole office may share one public address.
"""

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import EmailNotVerifiedError, NotAuthenticatedError, TooManyAttemptsError
from app.core.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    verify_password,
    waste_time_like_a_verify,
)
from app.models import AuthSession, LoginAttempt, User, utc_now

MAX_FAILURES = 5
MAX_FAILURES_PER_IP = 50
FAILURE_WINDOW = timedelta(minutes=15)

#: A session's expiry is pushed forward at most this often, so an active
#: user does not cause a database write on every single request.
RENEW_AFTER = timedelta(hours=1)

WRONG_CREDENTIALS = "wrong email or password"


def normalize_email(email: str) -> str:
    """Addresses compare case-insensitively: "Anna@Example.ORG" is "anna@example.org"."""
    return email.strip().lower()


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == normalize_email(email))).first()


def _recent_failures(db: Session, ip: str, email: str | None = None) -> int:
    """Failures from `ip` within the window: for `email`, or on any address."""
    since = utc_now() - FAILURE_WINDOW
    stmt = (
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.ip == ip, LoginAttempt.attempted_at >= since)
    )
    if email is not None:
        stmt = stmt.where(LoginAttempt.email == email)
    return db.scalar(stmt) or 0


def _forget_old_failures(db: Session) -> None:
    """Housekeeping: attempts older than the window no longer count."""
    db.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < utc_now() - FAILURE_WINDOW))


def authenticate(db: Session, *, email: str, password: str, ip: str) -> User:
    """The user these credentials belong to, or NotAuthenticatedError.

    The same error for an unknown address, a wrong password and a disabled
    account, and about the same time taken for each.
    """
    email = normalize_email(email)
    if (
        _recent_failures(db, ip, email) >= MAX_FAILURES
        or _recent_failures(db, ip) >= MAX_FAILURES_PER_IP
    ):
        raise TooManyAttemptsError("too many failed logins; try again later")

    user = find_user_by_email(db, email)
    if user is None or user.password_hash is None:
        waste_time_like_a_verify(password)
        ok = False
    else:
        ok = verify_password(user.password_hash, password) and user.is_active

    if not ok or user is None:
        db.add(LoginAttempt(email=email, ip=ip))
        _forget_old_failures(db)
        db.commit()
        raise NotAuthenticatedError(WRONG_CREDENTIALS)

    # Only now, after the right password: telling this to anyone who merely
    # guessed the address would reveal that the account exists.
    if user.email_verified_at is None:
        raise EmailNotVerifiedError("confirm your email address first")

    # Upgrade an old hash while the plain password is at hand.
    if user.password_hash is not None and needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    db.execute(delete(LoginAttempt).where(LoginAttempt.email == email, LoginAttempt.ip == ip))
    db.commit()
    return user


def create_session(db: Session, *, user: User, days: int, user_agent: str | None = None) -> str:
    """Start a session and return its token, which only the cookie holds.

    Also clears out everybody's expired sessions. Each one is deleted when
    its cookie comes back, but a browser that never returns would otherwise
    leave its row for ever; signing in is a fine moment to tidy up.
    """
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= utc_now()))
    token = new_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utc_now() + timedelta(days=days),
            user_agent=(user_agent or "")[:400] or None,
        )
    )
    db.commit()
    return token


def user_for_session(db: Session, token: str | None, *, days: int) -> User | None:
    """The signed-in user for a cookie's token, or None.

    Expired sessions are deleted when met. A live one is extended to `days`
    from now, at most once per RENEW_AFTER.
    """
    if not token:
        return None
    session = db.scalars(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    ).first()
    if session is None:
        return None

    now = utc_now()
    if session.expires_at <= now:
        db.delete(session)
        db.commit()
        return None

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None

    renewed = now + timedelta(days=days)
    if renewed - session.expires_at >= RENEW_AFTER:
        session.expires_at = renewed
        db.commit()
    return user


def end_session(db: Session, token: str | None) -> None:
    """Sign out: the token stops working at once, whatever the cookie says."""
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        db.commit()


def end_all_sessions(db: Session, user: User) -> None:
    """Sign a user out everywhere, e.g. when the account is disabled."""
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.commit()
