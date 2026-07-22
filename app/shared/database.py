"""Shared SQLAlchemy foundation for OpsForge.

This module defines the declarative base, metadata naming convention, and
reusable mixins that future ORM models inherit from.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.extensions import db

METADATA_NAMING_CONVENTION: dict[str, str] = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}

db.metadata.naming_convention = METADATA_NAMING_CONVENTION


def utcnow() -> datetime:
    """Return the current UTC timestamp.

    This helper keeps application-managed timestamps timezone-aware and
    consistent across SQLite and PostgreSQL.
    """

    return datetime.now(timezone.utc)


class Base(db.Model):  # type: ignore[name-defined]
    """Declarative ORM base for OpsForge models.

    Inherit from this class to ensure every model shares the same Flask-
    SQLAlchemy metadata and Alembic naming convention.
    """

    __abstract__ = True


class UUIDMixin:
    """Reusable UUID v4 primary key mixin.

    Inherit this mixin in models that should use a UUID primary key named
    ``id``.
    """

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TimestampMixin:
    """Reusable UTC timestamp mixin.

    Inherit this mixin in models that need ``created_at`` and ``updated_at``
    audit fields managed by SQLAlchemy.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class SoftDeleteMixin:
    """Reusable soft-delete timestamp mixin.

    Inherit this mixin only for entities that explicitly support logical
    deletion through a nullable ``deleted_at`` column.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class BaseModel(Base, UUIDMixin, TimestampMixin):
    """Abstract base for standard OpsForge entities.

    Inherit this class for future business entities that need the shared UUID
    primary key and UTC timestamps. Add :class:`SoftDeleteMixin` separately only
    for entities that explicitly allow soft delete.
    """

    __abstract__ = True


__all__ = [
    "Base",
    "BaseModel",
    "METADATA_NAMING_CONVENTION",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDMixin",
    "utcnow",
]

