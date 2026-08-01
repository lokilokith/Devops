"""Access domain models for OpsForge.

This module defines the AccessRequest entity for creating, tracking, and auditing
explicit requests for privileged credential or session access targets.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel

if TYPE_CHECKING:
    from app.identity.models import User
    from app.resources.models import Resource


class AccessRequestStatus(str, enum.Enum):
    """Approved lifecycle and review states for an access request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AccessRequest(BaseModel):
    """Authoritative ledger entry for an explicit privileged access request.

    Tracks a stable, human-readable identifier, the target asset vector, the
    temporary access window boundaries, and the mandatory compliance
    justification.
    """

    __tablename__ = "access_requests"

    __table_args__ = (
        CheckConstraint(
            "length(request_code) >= 3",
            name="ck_access_request_code_length",
        ),
        CheckConstraint(
            "requested_end_time > requested_start_time",
            name="ck_access_request_time_window_valid",
        ),
        CheckConstraint(
            "length(justification) >= 10",
            name="ck_access_request_justification_min_length",
        ),
    )

    request_code: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        unique=True,
        index=True,
    )

    requester_user_id: Mapped[UUID] = mapped_column(
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

    requested_start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    requested_end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    justification: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

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

    requester_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[requester_user_id],
    )

    resource: Mapped["Resource"] = relationship(
        "Resource",
        foreign_keys=[resource_id],
    )

    def __repr__(self) -> str:
        return (
            f"<AccessRequest(request_code={self.request_code!r}, "
            f"requester_user_id={self.requester_user_id!r}, "
            f"resource_id={self.resource_id!r}, "
            f"status={self.status.value!r})>"
        )


__all__ = [
    "AccessRequest",
    "AccessRequestStatus",
]
