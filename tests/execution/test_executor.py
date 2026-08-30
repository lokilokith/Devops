"""Tests for TargetExecutor and StubTargetExecutor."""

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
def make_request():
    def _factory(resource_id=None, operation=ExecutionOperation.VALIDATE_TARGET):
        rid = resource_id or uuid4()
        now = datetime.now(timezone.utc)
        auth_ctx = ExecutionAuthorizationContext(
            user_id=uuid4(),
            resource_id=rid,
            credential_id=uuid4(),
            requested_at=now,
            expires_at=now + timedelta(hours=1),
        )
        return ExecutionRequest(
            operation=operation,
            resource_id=rid,
            authorization_context=auth_ctx,
        )

    return _factory


def test_stub_executor_six_canonical_operations_success(make_request):
    executor = StubTargetExecutor()
    rid = uuid4()

    # 1. validate_target
    req_val = make_request(rid, ExecutionOperation.VALIDATE_TARGET)
    res_val = executor.validate_target(req_val)
    assert res_val.status == ExecutionStatus.SUCCESS
    assert res_val.verification_status == VerificationStatus.VERIFIED_SUCCESS

    # 2. provision_account
    req_prov = make_request(rid, ExecutionOperation.PROVISION_ACCOUNT)
    res_prov = executor.provision_account(req_prov)
    assert res_prov.status == ExecutionStatus.SUCCESS
    assert res_prov.verification_status == VerificationStatus.VERIFIED_SUCCESS

    # 3. remove_account
    req_rem = make_request(rid, ExecutionOperation.REMOVE_ACCOUNT)
    res_rem = executor.remove_account(req_rem)
    assert res_rem.status == ExecutionStatus.SUCCESS
    assert res_rem.verification_status == VerificationStatus.VERIFIED_SUCCESS

    # 4. rotate_credential
    req_rot = make_request(rid, ExecutionOperation.ROTATE_CREDENTIAL)
    res_rot = executor.rotate_credential(req_rot, b"old_secret_payload")
    assert res_rot.status == ExecutionStatus.SUCCESS
    assert res_rot.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert res_rot.new_secret_version is not None

    # 5. apply_jit_grant
    req_jit = make_request(rid, ExecutionOperation.APPLY_JIT_GRANT)
    res_jit = executor.apply_jit_grant(req_jit)
    assert res_jit.status == ExecutionStatus.SUCCESS
    assert res_jit.verification_status == VerificationStatus.VERIFIED_SUCCESS

    # 6. revoke_jit_grant
    req_rev = make_request(rid, ExecutionOperation.REVOKE_JIT_GRANT)
    res_rev = executor.revoke_jit_grant(req_rev)
    assert res_rev.status == ExecutionStatus.SUCCESS
    assert res_rev.verification_status == VerificationStatus.VERIFIED_SUCCESS


def test_stub_executor_failure_modes(make_request):
    rid_auth = uuid4()
    rid_authz = uuid4()
    rid_timeout = uuid4()
    rid_transport = uuid4()
    rid_target = uuid4()
    rid_verify = uuid4()
    rid_uncertain = uuid4()

    executor = StubTargetExecutor(
        behaviour_map={
            rid_auth: "auth_fail",
            rid_authz: "authz_fail",
            rid_timeout: "timeout",
            rid_transport: "transport_fail",
            rid_target: "target_fail",
            rid_verify: "verification_fail",
            rid_uncertain: "uncertain_state",
        }
    )

    with pytest.raises(TargetAuthenticationError):
        executor.validate_target(
            make_request(rid_auth, ExecutionOperation.VALIDATE_TARGET)
        )

    with pytest.raises(TargetAuthorizationError):
        executor.apply_jit_grant(
            make_request(rid_authz, ExecutionOperation.APPLY_JIT_GRANT)
        )

    with pytest.raises(ExecutionTimeoutError):
        executor.provision_account(
            make_request(rid_timeout, ExecutionOperation.PROVISION_ACCOUNT)
        )

    with pytest.raises(TransportError):
        executor.validate_target(
            make_request(rid_transport, ExecutionOperation.VALIDATE_TARGET)
        )

    with pytest.raises(TargetExecutionError):
        executor.remove_account(
            make_request(rid_target, ExecutionOperation.REMOVE_ACCOUNT)
        )

    # Verification failure returns explicit FAILED result with classification
    res_verify = executor.remove_account(
        make_request(rid_verify, ExecutionOperation.REMOVE_ACCOUNT)
    )
    assert res_verify.status == ExecutionStatus.FAILED
    assert res_verify.verification_status == VerificationStatus.VERIFIED_FAILURE
    assert (
        res_verify.failure_classification == FailureClassification.VERIFICATION_FAILURE
    )

    # Uncertain state returns UNCERTAIN status with is_uncertain=True
    res_unc = executor.provision_account(
        make_request(rid_uncertain, ExecutionOperation.PROVISION_ACCOUNT)
    )
    assert res_unc.status == ExecutionStatus.UNCERTAIN
    assert res_unc.is_uncertain is True
    assert res_unc.failure_classification == FailureClassification.UNCERTAIN_STATE


def test_executor_registry_lookup():
    rid_a = uuid4()
    rid_b = uuid4()

    exec_a = StubTargetExecutor({rid_a: "success"})
    exec_b = StubTargetExecutor({rid_b: "success"})

    registry = ExecutorRegistry([exec_a, exec_b])

    assert registry.get_executor(rid_a, ExecutionOperation.VALIDATE_TARGET) is exec_a
    assert registry.get_executor(rid_b, ExecutionOperation.PROVISION_ACCOUNT) is exec_b
    assert registry.get_executor(uuid4(), ExecutionOperation.VALIDATE_TARGET) is None
