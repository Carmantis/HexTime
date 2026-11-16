"""Declarative base, shared column types and mixins.

Two decisions live here and apply to every table:

* **UUID primary keys**, generated in Python. Autoincrement integers would
  collide if a local desktop database is ever merged into a server database,
  and they leak how many rows exist.
* **UTC-only timestamps**, enforced by :class:`UtcDateTime`.
"""

from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Dialect, TypeDecorator, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UtcDateTime(TypeDecorator[datetime]):
    """A timezone-aware datetime that is always UTC on both sides.

    SQLite cannot store an offset, so a value written as UTC comes back naive
    and comparisons silently go wrong. This type normalises both directions: it
    refuses naive input and always returns an aware UTC datetime, so identical
    code behaves identically on SQLite and PostgreSQL.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime rejected: store timezone-aware UTC, "
                "convert to local time only for display"
            )
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        # SQLite hands back a naive value that we know was written as UTC.
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utc_now() -> datetime:
    """Current time as an aware UTC datetime. Use instead of datetime.utcnow()."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for every model.

    ``type_annotation_map`` means a plain ``Mapped[datetime]`` annotation
    automatically becomes a UTC-normalising column — nobody has to remember.
    """

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: UtcDateTime,
        UUID: Uuid,
    }


class UuidPk:
    """Mixin giving a model a UUID v4 primary key generated in Python."""

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
