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
from app.execution.network_validator import (
    TargetAddressValidator,
    ValidatedTargetDestination,
)
from app.execution.ssh_executor import SSHTargetExecutor
from app.vault.ssh_keys import generate_ed25519_keypair


@pytest.fixture(autouse=True)
def mock_tcp_socket(monkeypatch):
    mock_sock = MagicMock(spec=socket.socket)
    monkeypatch.setattr(socket, "create_connection", lambda dest, timeout: mock_sock)
    return mock_sock


@pytest.fixture
def mock_validator():
    val = MagicMock(spec=TargetAddressValidator)
    val.validate_destination.return_value = ValidatedTargetDestination(
        original_host="10.0.0.1",
        resolved_ip="10.0.0.1",
        port=22,
        is_ipv6=False,
    )
    return val


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


@pytest.fixture
def test_keypair():
    return generate_ed25519_keypair()


def test_failure_injection_initial_connection_fails(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test initial connection failure maps to failed result."""
    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.connect.side_effect = paramiko.AuthenticationException("Auth failed")
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.rotate_credential(req, test_keypair[0].encode("utf-8"))
    assert res.status == ExecutionStatus.FAILED
    assert res.verification_status == VerificationStatus.VERIFIED_FAILURE
    assert res.failure_classification == FailureClassification.TARGET_FAILURE


def test_failure_injection_install_script_fails(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test target install script failure returns failed result."""
    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"PERMISSION DENIED"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b"Read-only file system"
    mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.rotate_credential(req, test_keypair[0].encode("utf-8"))
    assert res.status == ExecutionStatus.FAILED
    assert res.failure_classification == FailureClassification.TARGET_FAILURE
    assert "Failed during new public key installation" in res.error_message


def test_failure_injection_new_key_verification_fails_safe_rollback(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test new key failing verification marks VERIFICATION_FAILURE and preserves old key."""
    connect_calls = 0

    def fake_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 2:
            # Second connection is fresh connection with new key -> fail it
            raise paramiko.AuthenticationException("Permission denied (publickey)")
        return None

    def fake_exec_command(cmd):
        out = MagicMock()
        err = MagicMock()
        err.read.return_value = b""
        out.read.return_value = b"INSTALL_SUCCESS"
        return (MagicMock(), out, err)

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.connect.side_effect = fake_connect
    mock_client.exec_command.side_effect = fake_exec_command
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.rotate_credential(req, test_keypair[0].encode("utf-8"))
    assert res.status == ExecutionStatus.FAILED
    assert res.verification_status == VerificationStatus.VERIFIED_FAILURE
    assert res.failure_classification == FailureClassification.VERIFICATION_FAILURE
    assert "Old key preserved" in res.error_message


def test_failure_injection_old_key_removal_fails_marks_uncertain(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test failure during old key removal returns UNCERTAIN state."""
    connect_calls = 0

    def fake_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        return None

    def fake_exec_command(cmd):
        out = MagicMock()
        err = MagicMock()
        err.read.return_value = b""
        if "INSTALL_SUCCESS" in cmd:
            out.read.return_value = b"INSTALL_SUCCESS"
        elif "whoami" in cmd:
            out.read.return_value = b"opsforge-svc\n"
        elif "REMOVE_SUCCESS" in cmd:
            # Fail old key removal
            out.read.return_value = b"FAILED TO WRITE"
            err.read.return_value = b"Disk full"
        else:
            out.read.return_value = b""
        return (MagicMock(), out, err)

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.connect.side_effect = fake_connect
    mock_client.exec_command.side_effect = fake_exec_command
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.rotate_credential(req, test_keypair[0].encode("utf-8"))
    assert res.status == ExecutionStatus.FAILED
    assert res.verification_status == VerificationStatus.VERIFICATION_INDETERMINATE
    assert res.failure_classification == FailureClassification.UNCERTAIN_STATE
    assert res.is_uncertain is True
    assert "Failed during old key removal" in res.error_message


def test_failure_injection_old_key_not_revoked_fails(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test that if old key still authenticates after removal, rotation fails."""
    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.connect.return_value = None  # Always succeeds, even for old key

    def fake_exec_command(cmd):
        out = MagicMock()
        err = MagicMock()
        err.read.return_value = b""
        if "INSTALL_SUCCESS" in cmd:
            out.read.return_value = b"INSTALL_SUCCESS"
        elif "REMOVE_SUCCESS" in cmd:
            out.read.return_value = b"REMOVE_SUCCESS"
        elif "whoami" in cmd:
            out.read.return_value = b"opsforge-svc\n"
        else:
            out.read.return_value = b""
        return (MagicMock(), out, err)

    mock_client.exec_command.side_effect = fake_exec_command
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.rotate_credential(req, test_keypair[0].encode("utf-8"))
    assert res.status == ExecutionStatus.FAILED
    assert res.verification_status == VerificationStatus.VERIFIED_FAILURE
    assert res.failure_classification == FailureClassification.VERIFICATION_FAILURE
    assert "Old credential was not conclusively revoked" in res.error_message


def test_revocation_proof_distinguishes_network_failure_from_auth_failure(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test Critical Issue E: Network/Socket/Timeout failures are NOT treated as revocation."""
    connect_calls = 0

    def fake_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 4:
            # Step 5 (old key test) raises Transport/Network timeout rather than AuthenticationException!
            raise socket.timeout("Connection timed out")
        return None

    def fake_exec_command(cmd):
        out = MagicMock()
        err = MagicMock()
        err.read.return_value = b""
        if "INSTALL_SUCCESS" in cmd:
            out.read.return_value = b"INSTALL_SUCCESS"
        elif "REMOVE_SUCCESS" in cmd:
            out.read.return_value = b"REMOVE_SUCCESS"
        elif "whoami" in cmd:
            out.read.return_value = b"opsforge-svc\n"
        return (MagicMock(), out, err)

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.connect.side_effect = fake_connect
    mock_client.exec_command.side_effect = fake_exec_command
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.rotate_credential(req, test_keypair[0].encode("utf-8"))
    # MUST fail because timeout is not proof of revocation!
    assert res.status == ExecutionStatus.FAILED
    assert res.failure_classification == FailureClassification.VERIFICATION_FAILURE
    assert res.is_uncertain is True
    assert "Old credential was not conclusively revoked" in res.error_message


def test_failure_injection_final_new_key_verify_failure(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test Critical Issue D.F: Failure during final new-key verification fails closed."""
    connect_calls = 0

    def fake_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 4:
            # Step 5: old key correctly fails authentication
            raise paramiko.AuthenticationException("Permission denied")
        if connect_calls == 5:
            # Step 6: final new key verify fails unexpectedly
            raise paramiko.SSHException("Connection reset by peer")
        return None

    def fake_exec_command(cmd):
        out = MagicMock()
        err = MagicMock()
        err.read.return_value = b""
        if "INSTALL_SUCCESS" in cmd:
            out.read.return_value = b"INSTALL_SUCCESS"
        elif "REMOVE_SUCCESS" in cmd:
            out.read.return_value = b"REMOVE_SUCCESS"
        elif "whoami" in cmd:
            out.read.return_value = b"opsforge-svc\n"
        return (MagicMock(), out, err)

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.connect.side_effect = fake_connect
    mock_client.exec_command.side_effect = fake_exec_command
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.rotate_credential(req, test_keypair[0].encode("utf-8"))
    assert res.status == ExecutionStatus.FAILED
    assert res.failure_classification == FailureClassification.VERIFICATION_FAILURE
    assert res.is_uncertain is True
    assert "final authentication verification" in res.error_message
