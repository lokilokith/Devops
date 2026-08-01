"""Approval Workflow Models"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class ApprovalStatus(str, enum.Enum):
    """Lifecycle states for approval workflow."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalLevel(str, enum.Enum):
    """Levels of approval."""

    MANAGER = "manager"
    SECURITY = "security"
    SYSTEM_ADMIN = "system_admin"


class ApprovalWorkflow(BaseModel):
    """Approval record for an access request."""

    __tablename__ = "approval_workflows"

    access_request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approver_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    approval_level: Mapped[ApprovalLevel] = mapped_column(
        Enum(
            ApprovalLevel,
            name="approval_level_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(
            ApprovalStatus,
            name="approval_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=ApprovalStatus.PENDING,
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["ApprovalWorkflow", "ApprovalStatus", "ApprovalLevel"]
