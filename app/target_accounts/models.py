"""Target Account Binding domain models for OpsForge.

Implements Canonical Master Plan Item 9 (Target Account Provisioning) and Item 15 (Lifecycle).
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class TargetAccountBindingStatus(str, enum.Enum):
    """Lifecycle states for target account bindings (Item 15).

    PENDING: Binding requested/approved, target account creation & verification not complete.
    ACTIVE: Target account exists, public key installed, independently verified.
    SUSPENDED: User or binding suspended; OS account preserved for audit/forensics.
    REMOVED: Target OS account and credential verified removed.
    """

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class TargetAccountBinding(BaseModel):
    """Binds a Control Plane User to a dedicated OS account on a target Resource."""

    __tablename__ = "target_account_bindings"

    __table_args__ = (
        UniqueConstraint(
            "control_plane_user_id",
            "resource_id",
            name="uq_target_account_user_resource",
        ),
        UniqueConstraint(
            "resource_id",
            "target_os_username",
            name="uq_target_account_resource_os_user",
        ),
    )

    control_plane_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_os_username: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    ssh_credential_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vault_secrets.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    status: Mapped[TargetAccountBindingStatus] = mapped_column(
        Enum(
            TargetAccountBindingStatus,
            name="target_account_binding_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TargetAccountBindingStatus.PENDING,
        index=True,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    row_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    # Relationships
    user = relationship("User", foreign_keys=[control_plane_user_id])
    resource = relationship("Resource", foreign_keys=[resource_id])
    ssh_credential = relationship("VaultSecret", foreign_keys=[ssh_credential_id])
