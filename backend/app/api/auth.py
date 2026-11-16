"""Signing in and out, and the one-time email links.

Everything here except /auth/me exists only in server mode; local mode has no
accounts and answers 404. /auth/me works in both, so the frontend can always
ask who it is.
"""

from fastapi import APIRouter, Request, Response, status

from app.core.config import Settings
from app.core.deps import SESSION_COOKIE, CurrentUser, DbSession, ServerSettings
from app.core.email import MailerDep
from app.core.errors import TooManyAttemptsError
from app.core.rate_limit import RateLimiter
from app.models import User
from app.schemas.auth import (
    EmailRequest,
    LoginRequest,
    MeRead,
    RegisterRequest,
    SetPasswordRequest,
    TokenInfo,
    TokenRequest,
)
from app.services import accounts, auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    # Behind Caddy, uvicorn's --proxy-headers puts the real client here.
    return request.client.host if request.client else "unknown"


#: Requests to the forms that send email, per network address.
EMAIL_FORM_LIMIT = 10
EMAIL_FORM_WINDOW_SECONDS = 15 * 60


def email_form_limiter() -> RateLimiter:
    """A fresh limiter for one app (create_app keeps it in app.state)."""
    return RateLimiter(EMAIL_FORM_LIMIT, EMAIL_FORM_WINDOW_SECONDS)


def _limit_email_forms(request: Request) -> None:
    """Refuse a network address that keeps asking the server to send email."""
    limiter: RateLimiter = request.app.state.email_form_limiter
    if not limiter.allow(_client_ip(request)):
        raise TooManyAttemptsError("too many requests from this network; try again later")


def _sign_in(
    db: DbSession, request: Request, response: Response, settings: Settings, user: User
) -> None:
    """Start a session and hand its token to the browser as a cookie."""
    token = auth.create_session(
        db,
        user=user,
        days=settings.session_days,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=MeRead)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: ServerSettings,
) -> object:
    """Check the credentials and set the session cookie."""
    user = auth.authenticate(
        db, email=payload.email, password=payload.password, ip=_client_ip(request)
    )
    _sign_in(db, request, response, settings, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession, _settings: ServerSettings) -> None:
    """End this session. Works even if it had already expired."""
    auth.end_session(db, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=MeRead)
def me(user: CurrentUser) -> object:
    """Who the frontend is talking as."""
    return user


@router.post("/token", response_model=TokenInfo)
def read_token(payload: TokenRequest, db: DbSession, _settings: ServerSettings) -> object:
    """What a link from an email is for. POST, so the token stays out of logs."""
    user, purpose = accounts.inspect_token(db, payload.token)
    return TokenInfo(purpose=purpose, email=user.email, display_name=user.display_name)


@router.post("/password/set", response_model=MeRead)
def set_password(
    payload: SetPasswordRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: ServerSettings,
) -> object:
    """Choose a password through a setup or reset link, and sign in with it."""
    user = accounts.set_password(db, token=payload.token, password=payload.password)
    _sign_in(db, request, response, settings, user)
    return user


@router.post("/password/forgot", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(
    payload: EmailRequest,
    request: Request,
    db: DbSession,
    settings: ServerSettings,
    mailer: MailerDep,
) -> None:
    """204 whether or not the address has an account; 429 only from a flooding network."""
    _limit_email_forms(request)
    accounts.request_password_reset(db, email=payload.email, settings=settings, mailer=mailer)


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: DbSession,
    settings: ServerSettings,
    mailer: MailerDep,
) -> dict[str, str]:
    """Sign up, if allowed. 202: the email brings a link for choosing a password."""
    _limit_email_forms(request)
    accounts.register(
        db,
        email=payload.email,
        display_name=payload.display_name,
        settings=settings,
        mailer=mailer,
    )
    return {"status": "check_your_email"}


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(payload: TokenRequest, db: DbSession, _settings: ServerSettings) -> None:
    accounts.verify_email(db, token=payload.token)
