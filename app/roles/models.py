"""Role domain models for OpsForge.

This module defines the Role entity for the local authorization domain.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import Base, BaseModel, utcnow

if TYPE_CHECKING:
    from app.identity.models import User


class RoleType(str, enum.Enum):
    """Approved V1 role classification."""

    SYSTEM = "system"
    CUSTOM = "custom"


class RoleStatus(str, enum.Enum):
    """Approved V1 lifecycle state for roles."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    RETIRED = "retired"


class Role(BaseModel):
    """Business authorization category assigned to users.

    Role stores the stable business identity, human-readable label, type, and
    lifecycle state for a local authorization category. Membership is modeled
    separately in the role-user association layer in a later phase.
    """

    __tablename__ = "roles"

    # Recommended Change 4: Prevent invalid short codes at the DB layer
    __table_args__ = (
        CheckConstraint(
            "length(role_code) >= 3",
            name="ck_role_code_length",
        ),
    )

    # Recommended Change 1: Explicitly index unique columns for clarity & predictability
    role_code: Mapped[str] = mapped_column(
        String(60), nullable=False, unique=True, index=True
    )
    role_name: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    role_type: Mapped[RoleType] = mapped_column(
        Enum(
            RoleType,
            name="role_type_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=RoleType.CUSTOM,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[RoleStatus] = mapped_column(
        Enum(
            RoleStatus,
            name="role_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=RoleStatus.ACTIVE,
    )

    # Recommended Change 3: Improve debugging inspectability
    def __repr__(self) -> str:
        return f"<Role(role_code={self.role_code!r}, " f"role_name={self.role_name!r})>"

    @property
    def status_value(self) -> str:
        return self.status.value if hasattr(self.status, "value") else str(self.status)


class UserRole(Base):
    """Membership association between a User and a Role.

    This is the authoritative many-to-many bridge that grants a specific role
    to a specific user.
    """

    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Recommended Change 5: Added database-level fallback generation
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
        index=True,
    )

    # Kept completely unidirectional as recommended to avoid User model conflicts
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
    )
    role: Mapped["Role"] = relationship(
        "Role",
        foreign_keys=[role_id],
    )
    assigned_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[assigned_by_user_id],
    )

    # Recommended Change 3: Improve debugging inspectability
    def __repr__(self) -> str:
        return f"<UserRole(user_id={self.user_id!r}, " f"role_id={self.role_id!r})>"


__all__ = ["Role", "RoleStatus", "RoleType", "UserRole"]
