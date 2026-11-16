"""Schema for the configuration the frontend discovers at startup."""

from pydantic import BaseModel

from app.core.config import AppMode


class ConfigResponse(BaseModel):
    """Everything the frontend needs before it renders anything.

    The frontend never hardcodes the mode; it reads it from here and hides or
    shows the server-only features accordingly.
    """

    mode: AppMode
    locales: list[str]
    default_locale: str
    allowed_email_domain: str | None = None
    #: Whether the sign-in page offers "create an account" (server mode).
    allow_self_registration: bool = False
