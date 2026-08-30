"""Tests for Execution Plane Exception Hierarchy and Sanitization."""

from uuid import uuid4

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
    sanitize_error_message,
)


def test_sanitize_error_message():
    raw_1 = (
        "Authentication failed for user admin with password: SuperSecretPassword123!"
    )
    sanitized_1 = sanitize_error_message(raw_1)
    assert "SuperSecretPassword123!" not in sanitized_1
    assert "[REDACTED]" in sanitized_1

    raw_2 = "Failed to load private_key: -----BEGIN OPENSSH PRIVATE KEY-----"
    sanitized_2 = sanitize_error_message(raw_2)
    assert "-----BEGIN" not in sanitized_2
    assert "[REDACTED]" in sanitized_2

    raw_3 = "Invalid bearer token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz"
    sanitized_3 = sanitize_error_message(raw_3)
    assert "eyJhbGci" not in sanitized_3
    assert "[REDACTED]" in sanitized_3


def test_exception_hierarchy_and_properties():
    rid = uuid4()
    eid = uuid4()

    exc = TargetAuthenticationError(
        "SSH key error: secret_key=TopSecretKeyData",
        resource_id=rid,
        execution_id=eid,
    )
    assert isinstance(exc, ExecutionError)
    assert exc.resource_id == rid
    assert exc.execution_id == eid
    assert "TopSecretKeyData" not in str(exc)
    assert "[REDACTED]" in str(exc)


def test_all_execution_exceptions_inherit_from_execution_error():
    assert issubclass(TargetAuthenticationError, ExecutionError)
    assert issubclass(TargetAuthorizationError, ExecutionError)
    assert issubclass(ExecutionTimeoutError, ExecutionError)
    assert issubclass(TransportError, ExecutionError)
    assert issubclass(TargetExecutionError, ExecutionError)
    assert issubclass(VerificationFailureError, ExecutionError)
    assert issubclass(SecurityUncertaintyError, ExecutionError)
    assert issubclass(InvalidExecutionContextError, ExecutionError)
