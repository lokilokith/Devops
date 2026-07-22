"""Audit domain models for OpsForge.

This module defines the Audit log entity for immutable tracking, monitoring,
and compliance reporting of all privileged actions and security events.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel

if TYPE_CHECKING:
    from app.access.models import AccessRequest
    from app.approval.models import Approval
    from app.identity.models import User
    from app.resources.models import Resource


class AuditEventType(str, enum.Enum):
    """Supported audit event categorization types across the PAM platform."""

    LOGIN = "login"
    LOGOUT = "logout"
    ACCESS_REQUEST_CREATED = "access_request_created"
    ACCESS_REQUEST_APPROVED = "access_request_approved"
    ACCESS_REQUEST_DENIED = "access_request_denied"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    RESOURCE_CREATED = "resource_created"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_DELETED = "resource_deleted"
    PRIVILEGED_ACCESS_GRANTED = "privileged_access_granted"
    PRIVILEGED_ACCESS_REVOKED = "privileged_access_revoked"
    SECURITY_EVENT = "security_event"
    CONFIGURATION_CHANGE = "configuration_change"


class AuditSeverity(str, enum.Enum):
    """The severity or risk posture impact of an explicit audited security event."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditOutcome(str, enum.Enum):
    """The explicit structural result of the attempted operational action."""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class Audit(BaseModel):
    """Immutable ledger recording authoritative system, compliance, and security events.

    Tracks identity context, target resource state shifts, and global
    correlation identifiers to assure non-repudiation across distributed
    PAM orchestration flows.
    """

    __tablename__ = "audit_logs"

    __table_args__ = (
        CheckConstraint(
            "length(event_code) >= 3",
            name="ck_audit_event_code_length",
        ),
    )

    event_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(
            AuditEventType,
            name="audit_event_type_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    severity: Mapped[AuditSeverity] = mapped_column(
        Enum(
            AuditSeverity,
            name="audit_severity_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    outcome: Mapped[AuditOutcome] = mapped_column(
        Enum(
            AuditOutcome,
            name="audit_outcome_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    access_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_requests.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    approval_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    correlation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    actor_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[actor_user_id],
    )
    resource: Mapped["Resource"] = relationship(
        "Resource",
        foreign_keys=[resource_id],
    )
    access_request: Mapped["AccessRequest"] = relationship(
        "AccessRequest",
        foreign_keys=[access_request_id],
    )
    approval: Mapped["Approval"] = relationship(
        "Approval",
        foreign_keys=[approval_id],
    )

    def __repr__(self) -> str:
        return (
            f"<Audit(event_code={self.event_code!r}, "
            f"event_type={self.event_type.value!r}, "
            f"outcome={self.outcome.value!r})>"
        )


__all__ = [
    "Audit",
    "AuditOutcome",
    "AuditEventType",
    "AuditSeverity",
]


