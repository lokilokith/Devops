"""Automated credential non-disclosure and log-scraping tests for SSH Execution Plane."""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.execution.audit import ExecutionAuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    VerificationStatus,
)
from app.execution.exceptions import (
    TargetAuthenticationError,
    sanitize_error_message,
)
from app.execution.host_identity import HostKeyVerifier
from app.execution.ssh_executor import (
    SSHConnectionContext,
    SSHExecutionConfig,
)


@pytest.fixture
def sentinel_secrets():
    return [
        "SUPER_SECRET_SSH_PASSWORD_998877",
        "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIEowIBAAKCAQEA0fakeSentinelKeyData...\n-----END OPENSSH PRIVATE KEY-----",
        "SENTINEL_BEARER_TOKEN_xyz123abc",
        "PRIVATE_PASSPHRASE_secret_456",
    ]


def test_sanitize_error_message_redacts_sentinel_patterns(sentinel_secrets):
    """Test that sanitize_error_message redacts sensitive key=value patterns."""
    for secret in sentinel_secrets:
        raw_msg = f"Failed to authenticate with password: {secret} and token={secret}"
        sanitized = sanitize_error_message(raw_msg)
        assert secret not in sanitized
        assert "[REDACTED]" in sanitized


def test_execution_request_and_result_to_safe_dict_never_contains_secrets(
    sentinel_secrets,
):
    """Test that ExecutionRequest and ExecutionResult serialization scrubs secrets."""
    now = datetime.now(timezone.utc)
    auth_ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "hostname_ip": "10.0.0.1",
            "password": sentinel_secrets[0],
            "private_key": sentinel_secrets[1],
            "secret_token": sentinel_secrets[2],
            "public_param": "safe_value",
        },
    )

    safe_req = req.to_safe_dict()
    for secret in sentinel_secrets:
        assert secret not in str(safe_req)
    assert safe_req["parameters"]["public_param"] == "safe_value"
    assert "password" not in safe_req["parameters"]
    assert "private_key" not in safe_req["parameters"]

    res = ExecutionResult(
        execution_id=req.execution_id,
        operation=req.operation,
        status=ExecutionStatus.SUCCESS,
        verification_status=VerificationStatus.VERIFIED_SUCCESS,
        details={
            "safe_detail": "value",
            "secret_payload": sentinel_secrets[0],
            "private_data": sentinel_secrets[1],
        },
    )

    safe_res = res.to_safe_dict()
    for secret in sentinel_secrets:
        assert secret not in str(safe_res)
    assert safe_res["details"]["safe_detail"] == "value"
    assert "secret_payload" not in safe_res["details"]


def test_ssh_executor_log_scraping_on_auth_failure(caplog, sentinel_secrets):
    """Test that running SSH executor under logging never leaks credentials into captured logs."""
    caplog.set_level(logging.DEBUG)

    secret_pass = sentinel_secrets[0]
    secret_key = sentinel_secrets[1]

    mock_audit = MagicMock(spec=ExecutionAuditService)
    verifier = HostKeyVerifier()
    config = SSHExecutionConfig(connect_timeout=0.1)

    ctx = SSHConnectionContext(
        target_host="192.0.2.1",
        target_port=22,
        username="opsforge-svc",
        password=secret_pass,
        private_key_pem=secret_key,
        host_key_verifier=verifier,
        config=config,
        audit_service=mock_audit,
    )

    try:
        with ctx:
            pass
    except Exception:
        pass

    # Inspect all captured log text
    full_log = caplog.text
    for secret in sentinel_secrets:
        assert secret not in full_log, f"Found leaked secret in logs: {secret}"


def test_exception_hierarchy_sanitization(sentinel_secrets):
    """Test that all ExecutionError subclasses sanitize their message strings."""
    for secret in sentinel_secrets:
        raw = f"SSH key error: password={secret} private_key={secret}"
        exc = TargetAuthenticationError(raw)
        assert secret not in str(exc)
        assert secret not in exc.sanitized_message
        assert "[REDACTED]" in str(exc)
