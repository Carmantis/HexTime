"""Domain errors and the one error shape the API returns.

Services raise an :class:`AppError` subclass; the handler registered on the app
turns it into ``{"error": {"code": ..., "message": ...}}``. Routers never build
that envelope themselves, and the frontend translates ``code`` rather than
showing ``message`` to the user.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for errors that are part of the API contract."""

    code: str = "internal_error"
    status_code: int = 400

    def __init__(self, message: str | None = None) -> None:
        # The code doubles as a default message so every error has one.
        self.message = message or self.code
        super().__init__(self.message)


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class PermissionDeniedError(AppError):
    code = "permission_denied"
    status_code = 403


class NotAuthenticatedError(AppError):
    """No valid sign-in: no session cookie, an expired one, or a wrong password.

    One code for all of them, so a failed login never tells which part was
    wrong, nor whether the email address has an account.
    """

    code = "not_authenticated"
    status_code = 401


class TooManyAttemptsError(AppError):
    """Too many failed logins for this address from this network address."""

    code = "too_many_attempts"
    status_code = 429


class CsrfMissingError(AppError):
    """A state-changing request without the header only our own pages send."""

    code = "csrf_missing"
    status_code = 403


class ValidationFailedError(AppError):
    """A rule the request itself broke, not a missing or forbidden thing."""

    code = "validation_failed"
    status_code = 422


class InvalidTokenError(AppError):
    """A link that is unknown, already used or expired. The user needs a new one."""

    code = "invalid_token"
    status_code = 400


class CannotChangeSelfError(AppError):
    """An administrator may not disable or demote themselves: it is how an
    organisation ends up with no administrator at all."""

    code = "cannot_change_self"
    status_code = 409


class UserExistsError(AppError):
    """An address that already has an active account."""

    code = "user_exists"
    status_code = 409


class EmailDomainNotAllowedError(AppError):
    code = "email_domain_not_allowed"
    status_code = 422


class EmailNotVerifiedError(AppError):
    """Right password, but the address was never confirmed."""

    code = "email_not_verified"
    status_code = 403


class RegistrationClosedError(AppError):
    """Signing up yourself is off; people join when an administrator adds them."""

    code = "registration_closed"
    status_code = 403


class EmailFailedError(AppError):
    """The mail server refused or could not be reached. Worth retrying."""

    code = "email_failed"
    status_code = 502


class PasswordTooShortError(AppError):
    code = "password_too_short"
    status_code = 422


class EntryOverlapError(AppError):
    """Two time entries of the same user cover the same moment.

    Rejected rather than allowed: entries are billed, so an overlap means the
    same hour is invoiced twice and no report could tell.
    """

    code = "entry_overlap"
    status_code = 409


class TimerNotRunningError(AppError):
    """Asked to stop a timer when none was running."""

    code = "timer_not_running"
    status_code = 409


class AlreadyMemberError(AppError):
    """The person is in the team already."""

    code = "already_member"
    status_code = 409


class AlreadyInvitedError(AppError):
    """The person has an invitation to the team waiting already."""

    code = "already_invited"
    status_code = 409


class LastTeamLeadError(AppError):
    """A change would leave a team with no lead who can run it."""

    code = "last_team_lead"
    status_code = 409


class TeamHasEntriesError(AppError):
    """Deleting the team would take booked hours with its projects."""

    code = "team_has_entries"
    status_code = 409


def register_error_handlers(app: FastAPI) -> None:
    """Teach the app to render every AppError in the shared envelope."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Render FastAPI's own validation errors in the same envelope.

        Without this the API would speak two error languages: one for domain
        errors and FastAPI's ``{"detail": [...]}`` for a malformed request.
        The frontend translates ``code``, so there may only be one shape.
        """
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        return JSONResponse(
            status_code=ValidationFailedError.status_code,
            content={
                "error": {
                    "code": ValidationFailedError.code,
                    "message": "the request body or query string is invalid",
                    "fields": fields,
                }
            },
        )
