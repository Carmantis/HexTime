"""Audit log.

Every change to a time entry is written here with the value before and after,
so the history of booked hours can always be traced. Only an entry's owner
can change it. Stored in both modes; not shown in the UI yet.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UuidPk, utc_now


class AuditLog(UuidPk, Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)

    # SET NULL, not CASCADE: deleting a user must not erase the audit trail.
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[UUID]
    action: Mapped[str] = mapped_column(String(20))
    before_json: Mapped[str | None] = mapped_column(Text, default=None)
    after_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
