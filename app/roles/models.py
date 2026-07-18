"""Role domain models for OpsForge.

This module defines the Role entity for the local authorization domain.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import Base, BaseModel, utcnow


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

    role_code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    role_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
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
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )

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


__all__ = ["Role", "RoleStatus", "RoleType", "UserRole"]
