"""Execution Plane Domain Models and Contracts.

Defines the canonical Execution Plane contract for OpsForge PAM V1:
- Typed execution operations across the target lifecycle
- Structured execution requests with full authorization context
- Explicit execution results with fine-grained failure classifications
- Verification and security-uncertainty status representation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional
from uuid import UUID, uuid4


class ExecutionOperation(str, Enum):
    """Canonical PAM target-facing execution operations."""

    VALIDATE_TARGET = "VALIDATE_TARGET"
    PROVISION_ACCOUNT = "PROVISION_ACCOUNT"
    REMOVE_ACCOUNT = "REMOVE_ACCOUNT"
    ROTATE_CREDENTIAL = "ROTATE_CREDENTIAL"
    APPLY_JIT_GRANT = "APPLY_JIT_GRANT"
    REVOKE_JIT_GRANT = "REVOKE_JIT_GRANT"


class RotationStep(str, Enum):
    """Canonical durable state machine steps for credential rotation."""

    PENDING = "PENDING"
    INSTALLING = "INSTALLING"
    NEW_CREDENTIAL_VERIFIED = "NEW_CREDENTIAL_VERIFIED"
    REMOVING_OLD = "REMOVING_OLD"
    OLD_CREDENTIAL_REVOKED = "OLD_CREDENTIAL_REVOKED"
    VERIFIED = "VERIFIED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class ExecutionStatus(str, Enum):
    """High-level status of an execution operation."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


class FailureClassification(str, Enum):
    """Fine-grained classification of execution failures.

    Distinguishes operational failures from security uncertainty and
    transport/auth issues.
    """

    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    TIMEOUT = "TIMEOUT"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    TARGET_FAILURE = "TARGET_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    UNCERTAIN_STATE = "UNCERTAIN_STATE"
    CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"


class VerificationStatus(str, Enum):
    """Independent target-side verification status."""

    UNVERIFIED = "UNVERIFIED"
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    VERIFICATION_INDETERMINATE = "VERIFICATION_INDETERMINATE"


@dataclass(frozen=True)
class ExecutionAuthorizationContext:
    """Strongly-typed authorization proof required for target-facing execution.

    In accordance with Master Plan Item 14.1, an executor cannot be invoked
    with arbitrary credential or resource identifiers. The caller must prove
    the complete authorization chain.
    """

    user_id: UUID
    resource_id: UUID
    credential_id: UUID
    requested_at: datetime
    expires_at: datetime
    session_id: Optional[UUID] = None
    grant_id: Optional[UUID] = None
    target_account_binding_id: Optional[UUID] = None
    permissions: tuple[str, ...] = field(default_factory=tuple)

    def validate(self, current_time: Optional[datetime] = None) -> None:
        """Validate the authorization context against UTC wall-clock time.

        Raises:
            ValueError: If any required ID is missing or if the context is expired.
        """
        if not self.user_id:
            raise ValueError("Execution authorization context requires a valid user_id")
        if not self.resource_id:
            raise ValueError(
                "Execution authorization context requires a valid resource_id"
            )
        if not self.credential_id:
            raise ValueError(
                "Execution authorization context requires a valid credential_id"
            )

        now = current_time or datetime.now(timezone.utc)
        req_at = (
            self.requested_at
            if self.requested_at.tzinfo
            else self.requested_at.replace(tzinfo=timezone.utc)
        )
        exp_at = (
            self.expires_at
            if self.expires_at.tzinfo
            else self.expires_at.replace(tzinfo=timezone.utc)
        )

        if req_at > exp_at:
            raise ValueError(
                "Authorization context requested_at cannot be after expires_at"
            )

        if now > exp_at:
            raise ValueError("Execution authorization context has expired")

    def is_valid(self, current_time: Optional[datetime] = None) -> bool:
        """Return True if authorization context is currently valid, False otherwise."""
        try:
            self.validate(current_time)
            return True
        except ValueError:
            return False

    def to_safe_dict(self) -> dict[str, Any]:
        """Convert to a dictionary safe for auditing and logging (no secret material)."""
        return {
            "user_id": str(self.user_id),
            "resource_id": str(self.resource_id),
            "credential_id": str(self.credential_id),
            "session_id": str(self.session_id) if self.session_id else None,
            "grant_id": str(self.grant_id) if self.grant_id else None,
            "target_account_binding_id": (
                str(self.target_account_binding_id)
                if self.target_account_binding_id
                else None
            ),
            "requested_at": self.requested_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "permissions": list(self.permissions),
        }


@dataclass(frozen=True)
class ExecutionRequest:
    """Request submitted to the Execution Plane.

    Encapsulates the operation, target resource, authorization context, and
    operation parameters.
    """

    operation: ExecutionOperation
    resource_id: UUID
    authorization_context: ExecutionAuthorizationContext
    execution_id: UUID = field(default_factory=uuid4)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Validate request invariants on creation."""
        if not self.resource_id:
            raise ValueError("ExecutionRequest must specify a valid resource_id")
        if self.resource_id != self.authorization_context.resource_id:
            raise ValueError(
                f"Resource ID mismatch: request resource ({self.resource_id}) "
                f"does not match authorization context ({self.authorization_context.resource_id})"
            )
        self.authorization_context.validate()

    def to_safe_dict(self) -> dict[str, Any]:
        """Convert request to a sanitized dictionary for audit and logging."""
        sensitive_keywords = (
            "secret",
            "key",
            "password",
            "token",
            "credential",
            "payload",
            "bearer",
            "private",
        )
        return {
            "execution_id": str(self.execution_id),
            "operation": self.operation.value,
            "resource_id": str(self.resource_id),
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at.isoformat(),
            "authorization_context": self.authorization_context.to_safe_dict(),
            "parameters": {
                k: v
                for k, v in self.parameters.items()
                if not any(kw in k.lower() for kw in sensitive_keywords)
            },
        }


@dataclass(frozen=True)
class ExecutionResult:
    """Result returned by an execution operation.

    Carries explicit outcome status, failure classification, target verification
    state, and performance timing.
    """

    execution_id: UUID
    operation: ExecutionOperation
    status: ExecutionStatus
    verification_status: VerificationStatus
    failure_classification: Optional[FailureClassification] = None
    is_uncertain: bool = False
    error_message: Optional[str] = None
    details: Mapping[str, Any] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0
    new_secret_version: Optional[bytes] = None

    @property
    def is_success(self) -> bool:
        """Return True if execution succeeded and verified."""
        return (
            self.status == ExecutionStatus.SUCCESS
            and self.verification_status == VerificationStatus.VERIFIED_SUCCESS
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Convert result to a sanitized dictionary without secret material."""
        return {
            "execution_id": str(self.execution_id),
            "operation": self.operation.value,
            "status": self.status.value,
            "verification_status": self.verification_status.value,
            "failure_classification": (
                self.failure_classification.value
                if self.failure_classification
                else None
            ),
            "is_uncertain": self.is_uncertain,
            "details": {
                k: v
                for k, v in self.details.items()
                if not any(
                    kw in k.lower()
                    for kw in (
                        "secret",
                        "key",
                        "password",
                        "token",
                        "credential",
                        "payload",
                        "bearer",
                        "private",
                    )
                )
            },
            "executed_at": self.executed_at.isoformat(),
            "duration_ms": self.duration_ms,
        }
