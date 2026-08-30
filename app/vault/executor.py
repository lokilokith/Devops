"""Credential Executor Abstraction (Vault Bridge).

Defines the legacy rotation executor protocol and bridges to the canonical
6-method TargetExecutor protocol defined in app.execution.executor.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict
from uuid import UUID

import app.execution.domain as execution_domain
from app.execution.domain import (
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
    FailureClassification,
    VerificationStatus,
)
from app.execution.executor import TargetExecutor

CanonicalExecutionResult = execution_domain.ExecutionResult


class ExecutionResult(TypedDict, total=False):
    """Legacy result dictionary for credential rotation execution.

    * ``new_secret_version`` – opaque encrypted bytes stored as new secret payload.
    * ``metadata`` – optional auxiliary information.
    * ``error`` – optional error message for retryable failures.
    """

    new_secret_version: bytes
    metadata: dict[str, Any]
    error: str


class CredentialExecutor(Protocol):
    """Protocol for rotating a secret's underlying credential.

    Maintained for backwards compatibility with RotationWorker while conforming
    to the Execution Plane architecture.
    """

    def can_execute(self, resource_id: UUID) -> bool:
        """Return True if this executor knows how to rotate the given resource_id."""
        ...

    def execute(self, resource_id: UUID, current_secret: bytes) -> ExecutionResult:
        """Perform the rotation for resource_id."""
        ...


__all__ = [
    "ExecutionResult",
    "CredentialExecutor",
    "TargetExecutor",
    "CanonicalExecutionResult",
    "ExecutionOperation",
    "ExecutionStatus",
    "FailureClassification",
    "VerificationStatus",
    "ExecutionRequest",
]
