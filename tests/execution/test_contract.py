"""Tests for Execution Plane Domain Contracts and Models."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    FailureClassification,
    VerificationStatus,
)


@pytest.fixture
def valid_auth_context() -> ExecutionAuthorizationContext:
    user_id = uuid4()
    resource_id = uuid4()
    credential_id = uuid4()
    now = datetime.now(timezone.utc)
    return ExecutionAuthorizationContext(
        user_id=user_id,
        resource_id=resource_id,
        credential_id=credential_id,
        session_id=uuid4(),
        grant_id=uuid4(),
        target_account_binding_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=30),
        permissions=("EXECUTE", "ROTATE"),
    )


def test_valid_execution_authorization_context(valid_auth_context):
    assert valid_auth_context.is_valid() is True
    valid_auth_context.validate()
    safe_dict = valid_auth_context.to_safe_dict()
    assert safe_dict["user_id"] == str(valid_auth_context.user_id)
    assert safe_dict["resource_id"] == str(valid_auth_context.resource_id)
    assert safe_dict["credential_id"] == str(valid_auth_context.credential_id)
    assert "permissions" in safe_dict


def test_auth_context_expired_rejection(valid_auth_context):
    now = datetime.now(timezone.utc)
    expired_context = ExecutionAuthorizationContext(
        user_id=valid_auth_context.user_id,
        resource_id=valid_auth_context.resource_id,
        credential_id=valid_auth_context.credential_id,
        requested_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )
    assert expired_context.is_valid() is False
    with pytest.raises(ValueError, match="has expired"):
        expired_context.validate()


def test_auth_context_invalid_time_range():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="requested_at cannot be after expires_at"):
        ctx = ExecutionAuthorizationContext(
            user_id=uuid4(),
            resource_id=uuid4(),
            credential_id=uuid4(),
            requested_at=now + timedelta(hours=2),
            expires_at=now + timedelta(hours=1),
        )
        ctx.validate()


def test_auth_context_missing_ids():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="user_id"):
        ctx = ExecutionAuthorizationContext(
            user_id=None,  # type: ignore[arg-type]
            resource_id=uuid4(),
            credential_id=uuid4(),
            requested_at=now,
            expires_at=now + timedelta(hours=1),
        )
        ctx.validate()


def test_valid_execution_request(valid_auth_context):
    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=valid_auth_context.resource_id,
        authorization_context=valid_auth_context,
        parameters={"timeout_seconds": 10},
    )
    assert req.operation == ExecutionOperation.VALIDATE_TARGET
    assert req.resource_id == valid_auth_context.resource_id
    safe = req.to_safe_dict()
    assert safe["operation"] == "VALIDATE_TARGET"
    assert safe["resource_id"] == str(valid_auth_context.resource_id)


def test_execution_request_mismatched_resource_id_rejected(valid_auth_context):
    different_resource_id = uuid4()
    with pytest.raises(ValueError, match="Resource ID mismatch"):
        ExecutionRequest(
            operation=ExecutionOperation.PROVISION_ACCOUNT,
            resource_id=different_resource_id,
            authorization_context=valid_auth_context,
        )


def test_execution_request_secret_parameter_sanitization(valid_auth_context):
    req = ExecutionRequest(
        operation=ExecutionOperation.PROVISION_ACCOUNT,
        resource_id=valid_auth_context.resource_id,
        authorization_context=valid_auth_context,
        parameters={
            "account_name": "opsforge-svc",
            "db_password": "secret-value-never-log",
            "private_key": "private-key-material",
            "api_token": "token-xyz",
            "safe_param": "safe_value",
        },
    )
    safe = req.to_safe_dict()
    params = safe["parameters"]
    assert "safe_param" in params
    assert "account_name" in params
    assert "db_password" not in params
    assert "private_key" not in params
    assert "api_token" not in params


def test_execution_result_properties():
    res_id = uuid4()
    success_result = ExecutionResult(
        execution_id=res_id,
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        duration_ms=12.5,
    )
    assert success_result.is_success is True
    assert success_result.is_uncertain is False
    safe = success_result.to_safe_dict()
    assert safe["status"] == "SUCCESS"
    assert safe["verification_status"] == "VERIFIED_SUCCESS"

    uncertain_result = ExecutionResult(
        execution_id=res_id,
        operation=ExecutionOperation.REMOVE_ACCOUNT,
        status=ExecutionStatus.UNCERTAIN,
        verification_status=VerificationStatus.VERIFICATION_INDETERMINATE,
        failure_classification=FailureClassification.UNCERTAIN_STATE,
        is_uncertain=True,
        error_message="Rollback could not be confirmed",
    )
    assert uncertain_result.is_success is False
    assert uncertain_result.is_uncertain is True
    assert (
        uncertain_result.failure_classification == FailureClassification.UNCERTAIN_STATE
    )
