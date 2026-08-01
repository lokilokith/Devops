"""AccessRequest domain models for OpsForge."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class AccessRequestStatus(str, enum.Enum):
    """Lifecycle states for access requests."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AccessRequestPriority(str, enum.Enum):
    """Priority levels for access requests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AccessRequest(BaseModel):
    """Temporary access request for a role or resource."""

    __tablename__ = "access_requests"

    request_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    requester_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requested_role_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    requested_resource_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    business_justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AccessRequestStatus] = mapped_column(
        Enum(
            AccessRequestStatus,
            name="access_request_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=AccessRequestStatus.PENDING,
    )
    priority: Mapped[AccessRequestPriority] = mapped_column(
        Enum(
            AccessRequestPriority,
            name="access_request_priority_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=AccessRequestPriority.LOW,
    )
    requested_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    requested_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(requested_role_id IS NOT NULL) OR (requested_resource_id IS NOT NULL)",
            name="ck_ar_role_or_resource",
        ),
    )


__all__ = ["AccessRequest", "AccessRequestStatus", "AccessRequestPriority"]
