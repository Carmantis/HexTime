"""Public configuration endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import SUPPORTED_LOCALES, Settings, get_settings
from app.schemas.config import ConfigResponse

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigResponse)
def read_config(settings: Annotated[Settings, Depends(get_settings)]) -> ConfigResponse:
    """Return the runtime configuration the frontend reads on startup."""
    return ConfigResponse(
        mode=settings.app_mode,
        locales=list(SUPPORTED_LOCALES),
        default_locale=settings.default_locale,
        # Local mode has no registration, so the domain is meaningless there.
        allowed_email_domain=settings.allowed_email_domain if settings.is_server else None,
        allow_self_registration=settings.is_server and settings.allow_self_registration,
    )
