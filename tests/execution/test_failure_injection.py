"""Failure injection tests for SSH Execution Plane."""

import socket
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import paramiko
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
    TransportError,
)
from app.execution.network_validator import (
    TargetAddressValidator,
)
from app.execution.ssh_executor import (
    SSHConnectionContext,
    SSHExecutionConfig,
    SSHTargetExecutor,
)


@pytest.fixture
def auth_context():
    now = datetime.now(timezone.utc)
    return ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )


def test_failure_injection_unreachable_port(monkeypatch):
    """Inject connection refused / port closed error."""

    def fake_create_connection(dest, timeout):
        raise ConnectionRefusedError("Connection refused by target host")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)

    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, 2222, 9999}
    )
    ctx = SSHConnectionContext(
        target_host="127.0.0.1",
        target_port=9999,
        username="opsforge-svc",
        network_validator=validator,
    )

    with pytest.raises(TransportError, match="Network error connecting to"):
        with ctx:
            pass


def test_failure_injection_timeout(monkeypatch):
    """Inject network timeout during connection."""

    def fake_create_connection(dest, timeout):
        raise socket.timeout("Operation timed out")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)

    validator = TargetAddressValidator(allow_loopback=True)
    ctx = SSHConnectionContext(
        target_host="127.0.0.1",
        target_port=22,
        username="opsforge-svc",
        network_validator=validator,
    )

    with pytest.raises(ExecutionTimeoutError, match="Connection timed out"):
        with ctx:
            pass


def test_failure_injection_transport_handshake_drop(monkeypatch):
    """Inject transport drop during SSH handshake."""
    mock_sock = MagicMock(spec=socket.socket)
    monkeypatch.setattr(socket, "create_connection", lambda dest, timeout: mock_sock)

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.connect.side_effect = paramiko.SSHException("Connection reset by peer")
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    validator = TargetAddressValidator(allow_loopback=True)
    ctx = SSHConnectionContext(
        target_host="127.0.0.1",
        target_port=22,
        username="opsforge-svc",
        network_validator=validator,
    )

    with pytest.raises(TransportError, match="SSH protocol error connecting to"):
        with ctx:
            pass

    # Ensure socket was closed on failure
    mock_sock.close.assert_called_once()


def test_failure_injection_executor_maps_transport_failure(auth_context, monkeypatch):
    """Test SSHTargetExecutor.validate_target maps transport failure to failed ExecutionResult."""

    def fake_create_connection(dest, timeout):
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)

    validator = TargetAddressValidator(allow_loopback=True)
    executor = SSHTargetExecutor(network_validator=validator)

    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "127.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.validate_target(req)
    assert res.status == ExecutionStatus.FAILED
    assert res.verification_status == VerificationStatus.VERIFIED_FAILURE
    assert res.failure_classification == FailureClassification.TRANSPORT_FAILURE
    assert "Network error connecting to" in res.error_message


def test_failure_injection_concurrency_exhaustion(auth_context):
    """Test connection pool exhaustion raises timeout and maps properly."""
    config = SSHExecutionConfig(
        max_concurrent_connections=1, connection_pool_timeout=0.01
    )
    executor = SSHTargetExecutor(config=config)

    # Exhaust the single slot
    executor._semaphore.acquire()

    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "127.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.validate_target(req)
    assert res.status == ExecutionStatus.FAILED
    assert res.failure_classification == FailureClassification.TIMEOUT
    assert "Connection concurrency limit" in res.error_message
