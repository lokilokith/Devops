"""Compliance reporting models for OpsForge."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class ReportType(str, enum.Enum):
    """Types of compliance reports."""

    SOC2 = "soc2"
    ISO27001 = "iso27001"
    CUSTOM = "custom"


class ComplianceReport(BaseModel):
    """Security reporting."""

    __tablename__ = "compliance_reports"

    report_type: Mapped[ReportType] = mapped_column(
        Enum(
            ReportType,
            name="compliance_report_type_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    generated_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    report_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


__all__ = ["ComplianceReport", "ReportType"]
