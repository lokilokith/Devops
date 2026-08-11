"""Vault Lifecycle automation models for OpsForge."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class RotationStatus(str, enum.Enum):
    """Status of the secret rotation policy."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


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
    rotation_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_rotation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    rotation_script_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
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
