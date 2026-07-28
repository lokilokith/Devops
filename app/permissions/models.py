"""Permission domain models for OpsForge.

This module defines the Permission entity for the authorization domain.
"""

from __future__ import annotations

import enum
from sqlalchemy import CheckConstraint, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import BaseModel

class PermissionAction(str, enum.Enum):
    """Approved permission actions."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    MANAGE = "manage"

class PermissionStatus(str, enum.Enum):
    """Approved lifecycle state for permissions."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    RETIRED = "retired"

class Permission(BaseModel):
    """Granular authorization right tracked by OpsForge."""

    __tablename__ = "permissions"

    __table_args__ = (
        CheckConstraint(
            "length(permission_code) >= 3",
            name="ck_permission_code_length",
        ),
    )

    permission_code: Mapped[str] = mapped_column(
        String(60), nullable=False, unique=True, index=True
    )
    permission_name: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    action: Mapped[PermissionAction] = mapped_column(
        Enum(
            PermissionAction,
            name="permission_action_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=PermissionAction.READ,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[PermissionStatus] = mapped_column(
        Enum(
            PermissionStatus,
            name="permission_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=PermissionStatus.ACTIVE,
    )

    def __repr__(self) -> str:
        return (
            f"<Permission(permission_code={self.permission_code!r}, "
            f"permission_name={self.permission_name!r})>"
        )

__all__ = ["Permission", "PermissionStatus", "PermissionAction"]
