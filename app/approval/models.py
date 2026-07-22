"""Approval domain models for OpsForge.

This module defines the Approval entity for managing, tracking, and auditing
authorization decisions made against privileged access requests.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (CheckConstraint, DateTime, Enum, ForeignKey, Integer,
                        String)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel

if TYPE_CHECKING:
    from app.access.models import AccessRequest
    from app.identity.models import User
    from app.roles.models import Role


class ApprovalStatus(str, enum.Enum):
    """Approved lifecycle states for an individual approval decision step."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    DELEGATED = "delegated"


class Approval(BaseModel):
    """Authoritative ledger entry for an explicit privileged access
    approval decision step.

    Tracks the target request, governing workflow policy, assigned
    reviewers, actual decision maker, and the compliance payload of the
    evaluation.
    """

    __tablename__ = "approvals"

    __table_args__ = (
        CheckConstraint(
            "target_user_id IS NOT NULL OR target_role_id IS NOT NULL",
            name="ck_approval_target_assignment_present",
        ),
        CheckConstraint(
            "stage >= 1",
            name="ck_approval_stage_positive",
        ),
    )

    access_request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    approval_policy_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    target_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    target_role_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    approver_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    stage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(
            ApprovalStatus,
            name="approval_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [
                member.value for member in enum_cls
            ],
        ),
        nullable=False,
        index=True,
        default=ApprovalStatus.PENDING,
    )

    comments: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    decision_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    access_request: Mapped["AccessRequest"] = relationship(
        "AccessRequest",
        foreign_keys=[access_request_id],
    )

    target_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[target_user_id],
    )

    target_role: Mapped["Role | None"] = relationship(
        "Role",
        foreign_keys=[target_role_id],
    )

    approver_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[approver_user_id],
    )

    def __repr__(self) -> str:
        return (
            f"<Approval(id={self.id!r}, "
            f"access_request_id={self.access_request_id!r}, "
            f"stage={self.stage!r}, "
            f"status={self.status.value!r})>"
        )


__all__ = [
    "Approval",
    "ApprovalStatus",
]

