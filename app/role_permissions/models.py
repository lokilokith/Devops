"""RolePermission domain models for OpsForge.

This module defines the association between Roles and Permissions.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import Base, utcnow

if TYPE_CHECKING:
    from app.roles.models import Role
    from app.permissions.models import Permission
    from app.identity.models import User


class RolePermission(Base):
    """Membership association between a Role and a Permission."""

    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="RESTRICT"),
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
        server_default=func.now(),
        index=True,
    )

    role: Mapped["Role"] = relationship("Role", foreign_keys=[role_id])
    permission: Mapped["Permission"] = relationship(
        "Permission", foreign_keys=[permission_id]
    )
    assigned_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[assigned_by_user_id]
    )

    def __repr__(self) -> str:
        return (
            f"<RolePermission(role_id={self.role_id!r}, "
            f"permission_id={self.permission_id!r})>"
        )


__all__ = ["RolePermission"]
