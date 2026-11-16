"""Time entries — the heart of the application.

Duration is never stored. It is ``ended_at - started_at``, so the two can never
disagree. ``ended_at IS NULL`` means the timer is still running, and a partial
unique index makes a second running timer for the same user impossible at the
database level rather than only in the service.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, String, Table, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UuidPk, utc_now
from app.models.project import Tag

#: Many-to-many between entries and tags.
time_entry_tags = Table(
    "time_entry_tags",
    Base.metadata,
    Column(
        "time_entry_id",
        ForeignKey("time_entries.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

_RUNNING = text("ended_at IS NULL")


class TimeEntry(UuidPk, Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        # Report queries always filter by owner or project and then by date.
        Index("ix_time_entries_user_started", "user_id", "started_at"),
        Index("ix_time_entries_project_started", "project_id", "started_at"),
        # At most one running timer per user, enforced by the database.
        Index(
            "uq_time_entries_one_running_per_user",
            "user_id",
            unique=True,
            sqlite_where=_RUNNING,
            postgresql_where=_RUNNING,
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at > started_at",
            name="ck_time_entries_end_after_start",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Nullable so the timer can be started before picking a project.
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), default=None
    )
    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), default=None
    )
    description: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime] = mapped_column(default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(default=None)
    billable: Mapped[bool] = mapped_column(default=False)
    #: Copied from the project when the entry is created, so changing a project
    #: rate later never rewrites history.
    rate_snapshot_cents: Mapped[int | None] = mapped_column(default=None)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)

    #: "selectin" fetches the tags of every loaded entry in one extra query
    #: instead of one query per entry, which matters the moment a day view
    #: lists dozens of them.
    #: Tags are a set, not a sequence: a many-to-many relationship has no
    #: inherent order, so ordering by name makes reads deterministic instead
    #: of leaving it to whatever the database happens to return.
    tags: Mapped[list[Tag]] = relationship(
        secondary=time_entry_tags, lazy="selectin", order_by=Tag.name
    )

    @property
    def is_running(self) -> bool:
        return self.ended_at is None

    @property
    def duration(self) -> timedelta | None:
        """Elapsed time, or None while the timer is still running."""
        if self.ended_at is None:
            return None
        return self.ended_at - self.started_at

    @property
    def duration_seconds(self) -> int | None:
        duration = self.duration
        return None if duration is None else int(duration.total_seconds())
