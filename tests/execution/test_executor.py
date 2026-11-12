"""Tests for TargetExecutor interface, StubTargetExecutor implementation, and ExecutorRegistry."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
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
from app.execution.executor import ExecutorRegistry, StubTargetExecutor


@pytest.fixture
def auth_context():
    now = datetime.now(timezone.utc)
    return ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_stub_executor_six_canonical_operations_success(auth_context):
    executor = StubTargetExecutor()
    resource_id = auth_context.resource_id

    assert executor.can_execute(resource_id) is True

    # 1. Validate target
    req1 = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=resource_id,
        authorization_context=auth_context,
    )
    res1 = executor.validate_target(req1)
    assert res1.status == ExecutionStatus.SUCCESS
    assert res1.verification_status == VerificationStatus.VERIFIED_SUCCESS

    # 2. Provision account
    req2 = ExecutionRequest(
        operation=ExecutionOperation.PROVISION_ACCOUNT,
        resource_id=resource_id,
        authorization_context=auth_context,
    )
    res2 = executor.provision_account(req2)
    assert res2.status == ExecutionStatus.SUCCESS

    # 3. Remove account
    req3 = ExecutionRequest(
        operation=ExecutionOperation.REMOVE_ACCOUNT,
        resource_id=resource_id,
        authorization_context=auth_context,
    )
    res3 = executor.remove_account(req3)
    assert res3.status == ExecutionStatus.SUCCESS

    # 4. Rotate credential
    req4 = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=resource_id,
        authorization_context=auth_context,
    )
    res4 = executor.rotate_credential(req4, current_secret=b"old-secret")
    assert res4.status == ExecutionStatus.SUCCESS
    assert res4.new_secret_version is not None

    # 5. Apply JIT grant
    req5 = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=resource_id,
        authorization_context=auth_context,
    )
    res5 = executor.apply_jit_grant(req5)
    assert res5.status == ExecutionStatus.SUCCESS

    # 6. Revoke JIT grant
    req6 = ExecutionRequest(
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        resource_id=resource_id,
        authorization_context=auth_context,
    )
    res6 = executor.revoke_jit_grant(req6)
    assert res6.status == ExecutionStatus.SUCCESS


def test_stub_executor_failure_modes(auth_context):
    resource_id = auth_context.resource_id

    modes = {
        "auth_fail": TargetAuthenticationError,
        "authz_fail": TargetAuthorizationError,
        "timeout": ExecutionTimeoutError,
        "transport_fail": TransportError,
        "target_fail": TargetExecutionError,
    }

    for mode_name, expected_exception in modes.items():
        executor = StubTargetExecutor(behaviour_map={resource_id: mode_name})
        req = ExecutionRequest(
            operation=ExecutionOperation.VALIDATE_TARGET,
            resource_id=resource_id,
            authorization_context=auth_context,
        )
        with pytest.raises(expected_exception):
            executor.validate_target(req)

    # Verification failure result mode
    executor_vf = StubTargetExecutor(behaviour_map={resource_id: "verification_fail"})
    req_vf = ExecutionRequest(
        operation=ExecutionOperation.PROVISION_ACCOUNT,
        resource_id=resource_id,
        authorization_context=auth_context,
    )
    res_vf = executor_vf.provision_account(req_vf)
    assert res_vf.status == ExecutionStatus.FAILED
    assert res_vf.verification_status == VerificationStatus.VERIFIED_FAILURE

    # Uncertain state mode
    executor_unc = StubTargetExecutor(behaviour_map={resource_id: "uncertain_state"})
    req_unc = ExecutionRequest(
        operation=ExecutionOperation.REMOVE_ACCOUNT,
        resource_id=resource_id,
        authorization_context=auth_context,
    )
    res_unc = executor_unc.remove_account(req_unc)
    assert res_unc.status == ExecutionStatus.UNCERTAIN
    assert res_unc.is_uncertain is True
    assert res_unc.failure_classification == FailureClassification.UNCERTAIN_STATE


def test_stub_executor_legacy_execute(auth_context):
    resource_id = auth_context.resource_id
    executor = StubTargetExecutor(behaviour_map={resource_id: "success"})
    res = executor.execute(resource_id, b"current-secret")
    assert "new_secret_version" in res

    # Test retry and terminal modes
    executor_retry = StubTargetExecutor(behaviour_map={resource_id: "retry"})
    with pytest.raises(RuntimeError, match="retryable"):
        executor_retry.execute(resource_id, b"secret")

    executor_terminal = StubTargetExecutor(behaviour_map={resource_id: "terminal"})
    with pytest.raises(RuntimeError, match="terminal"):
        executor_terminal.execute(resource_id, b"secret")

    # Generic error mode in execute
    executor_custom = StubTargetExecutor(behaviour_map={resource_id: "unknown_error"})
    with pytest.raises(RuntimeError, match="Execution failed with mode"):
        executor_custom.execute(resource_id, b"secret")


def test_executor_registry_lookup():
    stub = StubTargetExecutor()
    registry = ExecutorRegistry()
    registry.register(stub)

    resource_id = uuid4()
    executor = registry.get_executor(resource_id, ExecutionOperation.VALIDATE_TARGET)
    assert executor is not None

    # Lookup without operation
    assert registry.get_executor(resource_id) is not None

    # Unknown resource when stub has restricted behaviour_map
    res2 = uuid4()
    restricted_stub = StubTargetExecutor(behaviour_map={resource_id: "success"})
    registry2 = ExecutorRegistry([restricted_stub])
    assert registry2.get_executor(res2, ExecutionOperation.VALIDATE_TARGET) is None
    assert registry2.get_executor(res2) is None
