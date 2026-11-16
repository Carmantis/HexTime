"""The organisation administrator's user list. Server mode, administrators only."""

from uuid import UUID

from fastapi import APIRouter, status

from app.core.deps import AdminUser, DbSession, ServerSettings
from app.core.email import MailerDep
from app.models import User
from app.schemas.admin import (
    AddPeopleRequest,
    AddPeopleResponse,
    AddResultRead,
    AdminUserRead,
    AdminUserUpdate,
)
from app.services import admin

router = APIRouter(prefix="/admin", tags=["admin"])


def _read(user: User) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        email=user.email or "",
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        status=admin.status_of(user),
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[AdminUserRead])
def list_users(_admin: AdminUser, db: DbSession) -> list[AdminUserRead]:
    return [_read(user) for user in admin.list_users(db)]


@router.post("/users", response_model=AddPeopleResponse)
def add_people(
    payload: AddPeopleRequest,
    _admin: AdminUser,
    db: DbSession,
    settings: ServerSettings,
    mailer: MailerDep,
) -> AddPeopleResponse:
    """Invite a list of people. 200 with a result per row, even if some failed."""
    results = admin.add_people(
        db,
        people=[admin.Person(p.email, p.display_name) for p in payload.people],
        settings=settings,
        mailer=mailer,
    )
    return AddPeopleResponse(
        results=[
            AddResultRead(
                email=r.email, display_name=r.display_name, outcome=r.outcome, user_id=r.user_id
            )
            for r in results
        ]
    )


@router.post("/users/{user_id}/send-link", status_code=status.HTTP_204_NO_CONTENT)
def send_link(
    user_id: UUID,
    _admin: AdminUser,
    db: DbSession,
    settings: ServerSettings,
    mailer: MailerDep,
) -> None:
    """A fresh link: to set the password, or to reset it if there is one."""
    admin.send_sign_in_link(db, user=admin.get_user(db, user_id), settings=settings, mailer=mailer)


@router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: UUID, payload: AdminUserUpdate, actor: AdminUser, db: DbSession
) -> AdminUserRead:
    """Disable or enable an account; grant or remove administrator rights."""
    user = admin.update_user(
        db,
        actor=actor,
        user=admin.get_user(db, user_id),
        is_active=payload.is_active,
        is_admin=payload.is_admin,
    )
    return _read(user)
