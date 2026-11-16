"""Request and response models for signing in."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import TokenPurpose


class LoginRequest(BaseModel):
    # Lengths only bound the input; the real checks are in the service.
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1000)


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class SetPasswordRequest(TokenRequest):
    password: str = Field(min_length=1, max_length=1000)


class RegisterRequest(BaseModel):
    """No password: the email's link lets the owner of the address choose one."""

    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(default="", max_length=200)


class TokenInfo(BaseModel):
    """What a link is for, so the page can greet the person before they type."""

    purpose: TokenPurpose
    email: str | None
    display_name: str


class MeRead(BaseModel):
    """The signed-in user, as the frontend needs them."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None
    display_name: str
    locale: str
    theme: str
    is_admin: bool


class MeUpdate(BaseModel):
    """What a user may change about themselves. Absent fields stay as they are."""

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    #: The language of emails and PDFs; the UI follows it too.
    locale: Literal["fi", "en"] | None = None
    theme: Literal["dark", "light"] | None = None
