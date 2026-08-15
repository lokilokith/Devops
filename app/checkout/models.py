"""Checkout domain models for OpsForge."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, CheckConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class LeaseStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    RETURNED = "returned"
    EXPIRED = "expired"
    REVOKED = "revoked"


class CredentialLease(BaseModel):
    """Represents a temporary, exclusive checkout of a VaultSecret."""

    __tablename__ = "credential_leases"
    
    __table_args__ = (
        Index(
            "ix_credential_leases_unique_active",
            "vault_secret_id",
            unique=True,
            postgresql_where=text("status = 'active'")
        ),
    )

    vault_secret_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vault_secrets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    access_request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("access_requests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    
    status: Mapped[LeaseStatus] = mapped_column(
        Enum(
            LeaseStatus,
            name="lease_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=LeaseStatus.PENDING,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["CredentialLease", "LeaseStatus"]
