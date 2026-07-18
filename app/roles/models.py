"""Role domain models for OpsForge.

This module defines the Role entity for the local authorization domain.
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import BaseModel


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


__all__ = ["Role", "RoleStatus", "RoleType"]
