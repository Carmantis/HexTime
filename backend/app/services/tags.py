"""Tags.

Like projects, tags are owned by exactly one of a user or a team and are
archived rather than deleted, so an old entry's tags keep their meaning.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailedError
from app.models import Tag, User
from app.models.base import utc_now
from app.models.project import DEFAULT_PROJECT_COLOR
from app.services import ownership
from app.services.sentinel import UNSET, Unset


def _guard_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValidationFailedError("name must not be empty")
    return stripped


def create_tag(
    db: Session,
    *,
    user: User,
    name: str,
    color: str = DEFAULT_PROJECT_COLOR,
    team_id: UUID | None = None,
) -> Tag:
    """The caller's own tag, or with `team_id` the team's (leads only)."""
    if team_id is not None:
        ownership.require_team_manager(db, user, team_id)
    tag = Tag(
        owner_user_id=None if team_id else user.id,
        owner_team_id=team_id,
        name=_guard_name(name),
        color=color,
    )
    db.add(tag)
    db.commit()
    return tag


def list_tags(db: Session, *, user: User, include_archived: bool = False) -> list[Tag]:
    stmt = select(Tag).where(ownership.visible_to(Tag, user))
    if not include_archived:
        stmt = stmt.where(Tag.archived_at.is_(None))
    return list(db.scalars(stmt.order_by(Tag.name)))


def get_tag(db: Session, tag_id: UUID, user: User) -> Tag:
    return ownership.require_visible(db, db.get(Tag, tag_id), user, "tag")


def get_changeable_tag(db: Session, tag_id: UUID, user: User) -> Tag:
    return ownership.require_changeable(db, db.get(Tag, tag_id), user, "tag")


def update_tag(
    db: Session,
    *,
    tag: Tag,
    name: str | Unset = UNSET,
    color: str | Unset = UNSET,
) -> Tag:
    # Neither field is nullable, so an explicit null is a mistake.
    for field, value in (("name", name), ("color", color)):
        if value is None:
            raise ValidationFailedError(f"{field} must not be null")

    if not isinstance(name, Unset):
        tag.name = _guard_name(name)
    if not isinstance(color, Unset):
        tag.color = color
    db.commit()
    return tag


def archive_tag(db: Session, *, tag: Tag) -> Tag:
    if tag.archived_at is None:
        tag.archived_at = utc_now()
        db.commit()
    return tag


def restore_tag(db: Session, *, tag: Tag) -> Tag:
    tag.archived_at = None
    db.commit()
    return tag
