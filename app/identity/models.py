"""User domain SQLAlchemy models for OpsForge V1."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class UserStatus(str, enum.Enum):
    """Approved V1 lifecycle states for local users."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    LOCKED = "locked"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class User(BaseModel):
    """Local OpsForge human account."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "manager_user_id IS NULL OR manager_user_id <> id",
            name="manager_not_self",
        ),
    )

    employee_id: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    username: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True, index=True
    )
    email: Mapped[str] = mapped_column(
        String(254), nullable=False, unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manager_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(
            UserStatus,
            name="user_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=UserStatus.ACTIVE,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    manager: Mapped["User | None"] = relationship(
        "User",
        remote_side=lambda: [User.id],
    )


__all__ = ["User", "UserStatus"]

