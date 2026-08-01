"""Audit domain models for OpsForge."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class AuditSeverity(str, enum.Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    DENIED = "denied"


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"

    event_id: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    target_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    request_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    approval_workflow_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AuditStatus] = mapped_column(
        Enum(
            AuditStatus,
            name="audit_status_enum",
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
    details: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)


__all__ = ["AuditLog", "AuditSeverity", "AuditStatus"]
