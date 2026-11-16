"""Tag routes."""

from uuid import UUID

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession
from app.schemas.tag import TagCreate, TagRead, TagUpdate
from app.services import tags

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
def read_tags(user: CurrentUser, db: DbSession, include_archived: bool = False) -> object:
    return tags.list_tags(db, user=user, include_archived=include_archived)


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
def add_tag(payload: TagCreate, user: CurrentUser, db: DbSession) -> object:
    return tags.create_tag(db, user=user, **payload.model_dump())


@router.get("/{tag_id}", response_model=TagRead)
def read_tag(tag_id: UUID, user: CurrentUser, db: DbSession) -> object:
    return tags.get_tag(db, tag_id, user)


@router.patch("/{tag_id}", response_model=TagRead)
def edit_tag(tag_id: UUID, payload: TagUpdate, user: CurrentUser, db: DbSession) -> object:
    tag = tags.get_changeable_tag(db, tag_id, user)
    return tags.update_tag(db, tag=tag, **payload.model_dump(exclude_unset=True))


@router.post("/{tag_id}/archive", response_model=TagRead)
def archive_tag(tag_id: UUID, user: CurrentUser, db: DbSession) -> object:
    tag = tags.get_changeable_tag(db, tag_id, user)
    return tags.archive_tag(db, tag=tag)


@router.post("/{tag_id}/restore", response_model=TagRead)
def restore_tag(tag_id: UUID, user: CurrentUser, db: DbSession) -> object:
    tag = tags.get_changeable_tag(db, tag_id, user)
    return tags.restore_tag(db, tag=tag)
