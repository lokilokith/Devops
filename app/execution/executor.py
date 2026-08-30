"""Target and Credential Executor Abstraction.

Defines the six-method CredentialExecutor / TargetExecutor protocol required
by Gate 1 of the OpsForge Canonical Master Plan, along with deterministic
stub implementations and the executor registry.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol, Tuple, Union
from uuid import UUID

from app.execution.domain import (
    ExecutionOperation,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    FailureClassification,
    VerificationStatus,
)
from app.execution.exceptions import (
    ExecutionTimeoutError,
    TargetAuthenticationError,
    TargetAuthorizationError,
    TargetExecutionError,
    TransportError,
)

logger = logging.getLogger(__name__)


class TargetExecutor(Protocol):
    """Protocol for target-facing Execution Plane operations.

    Defines the six canonical operations covering the full PAM target lifecycle.
    Implementations must be purely infrastructural and never depend on web
    frameworks, ORM models, or direct database connections.
    """

    def can_execute(self, resource_id: UUID, operation: ExecutionOperation) -> bool:
        """Return True if this executor supports the given operation on the target resource.

        Must be purely deterministic and in-memory (no network I/O).
        """
        ...

    def validate_target(self, request: ExecutionRequest) -> ExecutionResult:
        """Verify target reachability, host identity, and network trust boundaries."""
        ...

    def provision_account(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute single sequenced account creation, public key installation, and manifest update."""
        ...

    def remove_account(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute single sequenced account disabling/removal, key revocation, and manifest update."""
        ...

    def rotate_credential(
        self, request: ExecutionRequest, current_secret: bytes
    ) -> ExecutionResult:
        """Execute add-then-verify-then-remove credential rotation against the target."""
        ...

    def apply_jit_grant(self, request: ExecutionRequest) -> ExecutionResult:
        """Install helper-mediated, pre-validated sudoers grant on target."""
        ...

    def revoke_jit_grant(self, request: ExecutionRequest) -> ExecutionResult:
        """Remove sudoers grant and verify privilege revocation on target."""
        ...


class StubTargetExecutor:
    """Deterministic, in-memory test double implementing the TargetExecutor protocol.

    Used in testing and simulated environments to verify Execution Plane contracts
    without initiating live network connections.
    """

    def __init__(
        self,
        behaviour_map: Optional[
            Dict[
                Union[UUID, Tuple[UUID, ExecutionOperation]],
                str,
            ]
        ] = None,
        default_mode: str = "success",
    ) -> None:
        """Initialize the stub executor.

        Args:
            behaviour_map: Mapping of resource_id or (resource_id, operation) to behavior mode.
                Supported modes:
                - "success": Successful execution with verified state.
                - "auth_fail": Authentication failure (bad key / host-key mismatch).
                - "authz_fail": Authorization failure on target.
                - "timeout": Target operation timeout.
                - "transport_fail": Network / connectivity failure.
                - "target_fail": Target helper execution failure.
                - "verification_fail": Post-execution verification failure.
                - "uncertain_state": Security uncertainty / interrupted rollback.
                - "retry": RuntimeError with "retryable" (for legacy worker compatibility).
                - "terminal": RuntimeError with "terminal" (for legacy worker compatibility).
            default_mode: Fallback mode if resource_id is known but not explicitly configured.
        """
        self._behaviour: Dict[Any, str] = behaviour_map or {}
        self._default_mode = default_mode

    def _resolve_mode(self, resource_id: UUID, operation: ExecutionOperation) -> str:
        """Resolve behavior mode for a given resource and operation."""
        key_op = (resource_id, operation)
        if key_op in self._behaviour:
            return self._behaviour[key_op]
        if resource_id in self._behaviour:
            return self._behaviour[resource_id]
        return self._default_mode

    def can_execute(
        self, resource_id: UUID, operation: Optional[ExecutionOperation] = None
    ) -> bool:
        """Return True if executor handles the resource."""
        if not self._behaviour:
            return True
        if operation:
            if (resource_id, operation) in self._behaviour:
                return True
        return resource_id in self._behaviour

    def _execute_generic(
        self,
        request: ExecutionRequest,
        operation: ExecutionOperation,
        current_secret: Optional[bytes] = None,
    ) -> ExecutionResult:
        """Internal generic dispatch for stub execution."""
        start_time = time.monotonic()
        mode = self._resolve_mode(request.resource_id, operation)
        duration_ms = (time.monotonic() - start_time) * 1000.0

        if mode == "success":
            new_secret = None
            if operation == ExecutionOperation.ROTATE_CREDENTIAL:
                new_secret = (
                    f"new-secret-{request.resource_id}-{uuid.uuid4().hex[:8]}".encode()
                )

            return ExecutionResult(
                execution_id=request.execution_id,
                operation=operation,
                status=ExecutionStatus.SUCCESS,
                verification_status=VerificationStatus.VERIFIED_SUCCESS,
                details={"executor": "StubTargetExecutor", "mode": "success"},
                duration_ms=duration_ms,
                new_secret_version=new_secret,
            )

        if mode == "auth_fail":
            raise TargetAuthenticationError(
                "SSH authentication failed: host key verification failed or key rejected",
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            )

        if mode == "authz_fail":
            raise TargetAuthorizationError(
                "Target privilege elevation denied by security policy",
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            )

        if mode == "timeout":
            raise ExecutionTimeoutError(
                "Execution operation timed out after 30.0s",
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            )

        if mode == "transport_fail":
            raise TransportError(
                "Connection refused or unreachable target host",
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            )

        if mode == "target_fail":
            raise TargetExecutionError(
                "Target helper exited with non-zero status code 1",
                resource_id=request.resource_id,
                execution_id=request.execution_id,
            )

        if mode == "verification_fail":
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=operation,
                status=ExecutionStatus.FAILED,
                verification_status=VerificationStatus.VERIFIED_FAILURE,
                failure_classification=FailureClassification.VERIFICATION_FAILURE,
                error_message="Target verification failed: expected state not found on target",
                details={"executor": "StubTargetExecutor", "mode": "verification_fail"},
                duration_ms=duration_ms,
            )

        if mode == "uncertain_state":
            return ExecutionResult(
                execution_id=request.execution_id,
                operation=operation,
                status=ExecutionStatus.UNCERTAIN,
                verification_status=VerificationStatus.VERIFICATION_INDETERMINATE,
                failure_classification=FailureClassification.UNCERTAIN_STATE,
                is_uncertain=True,
                error_message="Security uncertainty: operation interrupted and rollback could not be verified",
                details={"executor": "StubTargetExecutor", "mode": "uncertain_state"},
                duration_ms=duration_ms,
            )

        if mode == "retry":
            raise RuntimeError("Transient error – retryable")

        if mode == "terminal":
            raise RuntimeError("Permanent error – terminal")

        # Fallback to general failure
        return ExecutionResult(
            execution_id=request.execution_id,
            operation=operation,
            status=ExecutionStatus.FAILED,
            verification_status=VerificationStatus.VERIFIED_FAILURE,
            failure_classification=FailureClassification.TARGET_FAILURE,
            error_message=f"Unknown execution mode: {mode}",
            duration_ms=duration_ms,
        )

    def validate_target(self, request: ExecutionRequest) -> ExecutionResult:
        return self._execute_generic(request, ExecutionOperation.VALIDATE_TARGET)

    def provision_account(self, request: ExecutionRequest) -> ExecutionResult:
        return self._execute_generic(request, ExecutionOperation.PROVISION_ACCOUNT)

    def remove_account(self, request: ExecutionRequest) -> ExecutionResult:
        return self._execute_generic(request, ExecutionOperation.REMOVE_ACCOUNT)

    def rotate_credential(
        self, request: ExecutionRequest, current_secret: bytes
    ) -> ExecutionResult:
        return self._execute_generic(
            request, ExecutionOperation.ROTATE_CREDENTIAL, current_secret
        )

    def apply_jit_grant(self, request: ExecutionRequest) -> ExecutionResult:
        return self._execute_generic(request, ExecutionOperation.APPLY_JIT_GRANT)

    def revoke_jit_grant(self, request: ExecutionRequest) -> ExecutionResult:
        return self._execute_generic(request, ExecutionOperation.REVOKE_JIT_GRANT)

    # Legacy rotation execution adapter
    def execute(self, resource_id: UUID, current_secret: bytes) -> Dict[str, Any]:
        """Legacy compatibility method for Phase 0 rotation worker integration."""
        mode = self._behaviour.get(resource_id, "success")
        if mode == "success":
            fake_blob = f"{resource_id}-{uuid.uuid4()}".encode()
            return {
                "new_secret_version": fake_blob,
                "metadata": {"generated_by": "stub"},
                "error": "",
            }
        if mode == "retry":
            raise RuntimeError("Transient error – retryable")
        if mode == "terminal":
            raise RuntimeError("Permanent error – terminal")
        raise RuntimeError(f"Execution failed with mode {mode}")


class ExecutorRegistry:
    """Registry holding registered target executors.

    Matches requests to capable executors based on target resource and operation.
    """

    def __init__(self, executors: Optional[List[TargetExecutor]] = None) -> None:
        self._executors: List[TargetExecutor] = (
            executors if executors is not None else [StubTargetExecutor()]
        )

    def register(self, executor: TargetExecutor) -> None:
        """Register a new executor."""
        self._executors.append(executor)

    def get_executor(
        self, resource_id: UUID, operation: Optional[ExecutionOperation] = None
    ) -> Optional[TargetExecutor]:
        """Return the first executor capable of executing the operation for the resource."""
        for exe in self._executors:
            if operation:
                if exe.can_execute(resource_id, operation):
                    return exe
            else:
                if getattr(exe, "can_execute", None):
                    # Handle both 1-arg legacy and 2-arg signatures
                    try:
                        if exe.can_execute(
                            resource_id, ExecutionOperation.VALIDATE_TARGET
                        ):
                            return exe
                    except TypeError:
                        if exe.can_execute(resource_id):  # type: ignore[call-arg]
                            return exe
        return None
