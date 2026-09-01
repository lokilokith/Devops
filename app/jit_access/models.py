"""JIT Privileged Access domain models for OpsForge."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class JITGrantStatus(str, enum.Enum):
    """Lifecycle states for JIT Access Grants."""

    PENDING = "pending"
    ACTIVE = "active"
    REVOCATION_PENDING = "revocation_pending"
    REVOCATION_RUNNING = "revocation_running"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DENIED = "denied"
    FAILED = "failed"
    SECURITY_UNCERTAIN = "security_uncertain"


class JITAccessGrant(BaseModel):
    """Tracks temporary privileged access grants."""

    __tablename__ = "jit_access_grants"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_account_binding_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("target_account_bindings.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    command_set_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    approved_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    approval_request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[JITGrantStatus] = mapped_column(
        Enum(
            JITGrantStatus,
            name="jit_grant_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=JITGrantStatus.PENDING,
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_complete: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observed_overrun_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revocation_worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revocation_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sessions_terminated: Mapped[int | None] = mapped_column(Integer, nullable=True)


class JITAccessSession(BaseModel):
    """Tracks ephemeral credentials and active sessions created for Just-In-Time access."""

    __tablename__ = "jit_access_sessions"

    access_request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    ephemeral_secret_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vault_secrets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    jit_grant_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jit_access_grants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resource_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_os_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_session_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def expire(self) -> bool:
        """Expire the session. Returns True if state changed, False if already expired."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        if self.revoked_at is not None:
            raise ValueError("Cannot expire a revoked session.")
        # Need to handle offset-naive datetime gracefully if it occurs
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            return False
        self.expires_at = now
        self.status = "expired"
        return True

    def revoke(self) -> bool:
        """Revoke the session. Returns True if state changed, False if already revoked."""
        from datetime import datetime, timezone

        if self.revoked_at is not None:
            return False
        self.revoked_at = datetime.now(timezone.utc)
        self.status = "revoked"
        return True


__all__ = ["JITAccessGrant", "JITGrantStatus", "JITAccessSession"]
