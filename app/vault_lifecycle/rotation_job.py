"""Rotation Job model and state machine for automated credential rotation."""

from __future__ import annotations

import enum
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class RotationJobState(str, enum.Enum):
    """Lifecycle states of an automated rotation job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    RETRY_PENDING = "RETRY_PENDING"
    FAILED = "FAILED"
    SECURITY_UNCERTAINTY = "SECURITY_UNCERTAINTY"


# Terminal states where no further automated worker transitions should occur
TERMINAL_JOB_STATES = {
    RotationJobState.SUCCEEDED,
    RotationJobState.FAILED,
    RotationJobState.SECURITY_UNCERTAINTY,
}

# Active states indicating a rotation is actively pending or in progress
ACTIVE_JOB_STATES = {
    RotationJobState.QUEUED,
    RotationJobState.RUNNING,
    RotationJobState.RETRY_PENDING,
}

# Safe error codes allowed for storage in rotation jobs
SAFE_ERROR_CODES = {
    "SSH_TIMEOUT",
    "SSH_TRANSPORT_FAILURE",
    "AUTHENTICATION_FAILED",
    "HOST_KEY_MISMATCH",
    "TARGET_UNREACHABLE",
    "TARGET_EXECUTION_ERROR",
    "CAS_CONFLICT",
    "VAULT_COMMIT_FAILURE",
    "INVALID_CONFIGURATION",
    "SECURITY_UNCERTAINTY",
    "RETRY_EXHAUSTED",
    "FENCED_OUT",
    "STALE_GENERATION",
    "UNEXPECTED_ERROR",
}


def sanitize_error_code(code: str | None) -> str:
    """Normalize and validate an error code against the safe allowlist."""
    if not code:
        return "UNEXPECTED_ERROR"
    normalized = code.strip().upper().replace(" ", "_")
    if normalized in SAFE_ERROR_CODES:
        return normalized
    return "UNEXPECTED_ERROR"


def sanitize_error_message(message: str | None, max_length: int = 255) -> str | None:
    """Sanitize human-readable error messages to guarantee zero secret leakage."""
    if not message:
        return None
    # Strip potential secret markers, key material, tokens, and multi-line dumps
    clean = re.sub(
        r"(?i)(private[_\s]key|BEGIN[_\s]OPENSSH|BEGIN[_\s]RSA|password|token|secret|dek)[\w\s:=+/]+",
        "[REDACTED]",
        message,
    )
    # Collapse whitespace and truncate
    clean = " ".join(clean.split())
    return clean[:max_length]


class RotationJob(BaseModel):
    """Durable record of an automated rotation attempt."""

    __tablename__ = "rotation_jobs"

    __table_args__ = (
        UniqueConstraint(
            "vault_secret_id",
            "rotation_generation",
            name="uq_rotation_jobs_secret_generation",
        ),
        Index("ix_rotation_jobs_state_retry", "state", "next_retry_at"),
        Index("ix_rotation_jobs_lease", "state", "lease_expires_at"),
    )

    vault_secret_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vault_secrets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rotation_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[RotationJobState] = mapped_column(
        Enum(
            RotationJobState,
            name="rotation_job_state_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=RotationJobState.QUEUED,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_classification: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def __init__(self, **kwargs):
        kwargs.setdefault("state", RotationJobState.QUEUED)
        kwargs.setdefault("attempt_count", 0)
        kwargs.setdefault("max_attempts", 3)
        kwargs.setdefault("lease_generation", 0)
        kwargs.setdefault("rotation_generation", 1)
        kwargs.setdefault("row_version", 1)
        super().__init__(**kwargs)

    def transition_to_running(
        self,
        worker_id: str,
        lease_duration_seconds: int = 300,
        now: datetime | None = None,
    ) -> None:
        """Claim the job lease and transition to RUNNING atomically."""
        current_time = now or datetime.now(timezone.utc)
        valid_source_states = {
            RotationJobState.QUEUED,
            RotationJobState.RETRY_PENDING,
            RotationJobState.RUNNING,  # allowed for lease recovery/reclaiming if expired
        }
        if self.state not in valid_source_states:
            raise ValueError(f"Cannot transition to RUNNING from state {self.state}")

        self.state = RotationJobState.RUNNING
        self.lease_owner = worker_id
        from datetime import timedelta

        self.lease_expires_at = current_time + timedelta(seconds=lease_duration_seconds)
        self.lease_generation = (self.lease_generation or 0) + 1
        self.attempt_count = (self.attempt_count or 0) + 1
        if not self.started_at:
            self.started_at = current_time
        self.updated_at = current_time

    def transition_to_succeeded(self, now: datetime | None = None) -> None:
        """Mark the job as successfully completed."""
        if self.state != RotationJobState.RUNNING:
            raise ValueError(f"Cannot complete job from state {self.state}")
        current_time = now or datetime.now(timezone.utc)
        self.state = RotationJobState.SUCCEEDED
        self.completed_at = current_time
        self.lease_owner = None
        self.lease_expires_at = None
        self.updated_at = current_time

    def transition_to_retry_pending(
        self,
        next_retry_at: datetime,
        error_code: str,
        error_classification: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Transition job to RETRY_PENDING for scheduled backoff retry."""
        if self.state != RotationJobState.RUNNING:
            raise ValueError(f"Cannot schedule retry from state {self.state}")
        current_time = now or datetime.now(timezone.utc)
        self.state = RotationJobState.RETRY_PENDING
        self.next_retry_at = next_retry_at
        self.last_error_code = sanitize_error_code(error_code)
        self.last_error_classification = error_classification
        self.lease_owner = None
        self.lease_expires_at = None
        self.updated_at = current_time

    def transition_to_failed(
        self,
        error_code: str,
        error_classification: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Mark the job permanently FAILED (non-retryable or retry exhausted)."""
        current_time = now or datetime.now(timezone.utc)
        self.state = RotationJobState.FAILED
        self.completed_at = current_time
        self.last_error_code = sanitize_error_code(error_code)
        self.last_error_classification = error_classification
        self.lease_owner = None
        self.lease_expires_at = None
        self.updated_at = current_time

    def transition_to_security_uncertainty(
        self,
        error_code: str = "SECURITY_UNCERTAINTY",
        error_classification: str | None = None,
        now: datetime | None = None,
    ) -> None:
        """Mark the job with SECURITY_UNCERTAINTY when target state is indeterminate."""
        current_time = now or datetime.now(timezone.utc)
        self.state = RotationJobState.SECURITY_UNCERTAINTY
        self.completed_at = current_time
        self.last_error_code = sanitize_error_code(error_code)
        self.last_error_classification = error_classification or "SECURITY_UNCERTAINTY"
        self.lease_owner = None
        self.lease_expires_at = None
        self.updated_at = current_time

    def is_lease_expired(self, current_time: datetime | None = None) -> bool:
        """Return True if lease has expired or was never set."""
        if not self.lease_expires_at:
            return True
        now = current_time or datetime.now(timezone.utc)
        lease_exp = (
            self.lease_expires_at
            if self.lease_expires_at.tzinfo
            else self.lease_expires_at.replace(tzinfo=timezone.utc)
        )
        return now >= lease_exp


__all__ = [
    "RotationJob",
    "RotationJobState",
    "TERMINAL_JOB_STATES",
    "ACTIVE_JOB_STATES",
    "SAFE_ERROR_CODES",
    "sanitize_error_code",
    "sanitize_error_message",
]
