"""Execution Plane Package.

Exports canonical execution domain models, protocols, exceptions, and audit services.
"""

from app.execution.audit import ExecutionAuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    FailureClassification,
    VerificationStatus,
)
from app.execution.exceptions import (
    ExecutionError,
    ExecutionTimeoutError,
    InvalidExecutionContextError,
    SecurityUncertaintyError,
    TargetAuthenticationError,
    TargetAuthorizationError,
    TargetExecutionError,
    TransportError,
    VerificationFailureError,
)
from app.execution.executor import ExecutorRegistry, StubTargetExecutor, TargetExecutor
from app.execution.host_identity import (
    HostKeyMismatchError,
    HostKeyVerificationError,
    HostKeyVerifier,
    TrustedHostKey,
    UntrustedHostError,
)
from app.execution.network_validator import (
    TargetAddressValidationError,
    TargetAddressValidator,
    ValidatedTargetDestination,
)
from app.execution.ssh_executor import (
    SSHConnectionContext,
    SSHExecutionConfig,
    SSHTargetExecutor,
)

__all__ = [
    "ExecutionOperation",
    "ExecutionStatus",
    "FailureClassification",
    "VerificationStatus",
    "ExecutionAuthorizationContext",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionError",
    "TargetAuthenticationError",
    "TargetAuthorizationError",
    "ExecutionTimeoutError",
    "TransportError",
    "TargetExecutionError",
    "VerificationFailureError",
    "SecurityUncertaintyError",
    "InvalidExecutionContextError",
    "TargetExecutor",
    "StubTargetExecutor",
    "ExecutorRegistry",
    "ExecutionAuditService",
    "TargetAddressValidator",
    "ValidatedTargetDestination",
    "TargetAddressValidationError",
    "HostKeyVerifier",
    "TrustedHostKey",
    "HostKeyVerificationError",
    "HostKeyMismatchError",
    "UntrustedHostError",
    "SSHExecutionConfig",
    "SSHConnectionContext",
    "SSHTargetExecutor",
]
