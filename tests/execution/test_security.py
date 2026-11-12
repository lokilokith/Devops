"""Security Invariant Tests for Execution Plane Contracts."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    VerificationStatus,
)


def test_cannot_create_execution_request_without_valid_auth_context():
    now = datetime.now(timezone.utc)
    expired_ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="has expired"):
        ExecutionRequest(
            operation=ExecutionOperation.VALIDATE_TARGET,
            resource_id=expired_ctx.resource_id,
            authorization_context=expired_ctx,
        )


def test_cannot_create_execution_request_with_mismatched_resource():
    now = datetime.now(timezone.utc)
    ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )
    unauthorized_resource = uuid4()

    with pytest.raises(ValueError, match="Resource ID mismatch"):
        ExecutionRequest(
            operation=ExecutionOperation.VALIDATE_TARGET,
            resource_id=unauthorized_resource,
            authorization_context=ctx,
        )


def test_execution_request_serialization_never_leaks_secrets():
    now = datetime.now(timezone.utc)
    ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(hours=1),
    )
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=ctx.resource_id,
        authorization_context=ctx,
        parameters={
            "target_host": "10.0.0.1",
            "ssh_password": "super-secret-password-123",
            "private_key_data": "raw-key-content",
            "credential_payload": "sensitive-credential",
            "port": 22,
        },
    )

    safe = req.to_safe_dict()
    serialized = str(safe)
    assert "super-secret-password-123" not in serialized
    assert "raw-key-content" not in serialized
    assert "sensitive-credential" not in serialized
    assert safe["parameters"]["target_host"] == "10.0.0.1"
    assert safe["parameters"]["port"] == 22


def test_execution_result_serialization_never_leaks_secrets():
    res = ExecutionResult(
        execution_id=uuid4(),
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        new_secret_version=b"raw-ephemeral-secret-bytes-do-not-serialize",
        details={
            "target_user": "opsforge-svc",
            "auth_token": "secret-auth-token",
            "status": "active",
        },
    )

    safe = res.to_safe_dict()
    serialized = str(safe)
    assert "raw-ephemeral-secret-bytes" not in serialized
    assert "secret-auth-token" not in serialized
    assert safe["details"]["target_user"] == "opsforge-svc"
