"""Vault Lifecycle automation models for OpsForge."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class RotationStatus(str, enum.Enum):
    """Status of the secret rotation policy."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class RotationResultStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"


class SecretRotationPolicy(BaseModel):
    """Vault lifecycle automation."""

    __tablename__ = "secret_rotation_policies"

    vault_secret_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vault_secrets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plugin_name: Mapped[str] = mapped_column(String(100), nullable=False, default="manual")
    rotation_interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    rotation_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_rotation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    rotation_script_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    last_rotation_status: Mapped[RotationResultStatus | None] = mapped_column(
        Enum(
            RotationResultStatus,
            name="rotation_result_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[RotationStatus] = mapped_column(
        Enum(
            RotationStatus,
            name="rotation_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=RotationStatus.ACTIVE,
    )

__all__ = ["SecretRotationPolicy", "RotationStatus"]
