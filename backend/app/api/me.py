"""The signed-in user's own profile. Both modes: the desktop user has one too."""

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.auth import MeRead, MeUpdate
from app.services import users

router = APIRouter(prefix="/me", tags=["me"])


@router.patch("", response_model=MeRead)
def update_me(payload: MeUpdate, user: CurrentUser, db: DbSession) -> object:
    return users.update_profile(
        db,
        user=user,
        display_name=payload.display_name,
        locale=payload.locale,
        theme=payload.theme,
    )
