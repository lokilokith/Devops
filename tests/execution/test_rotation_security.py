import io
import logging
import socket
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import paramiko
import pytest

from app.execution.audit import ExecutionAuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
)
from app.execution.exceptions import TargetAuthorizationError
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


@pytest.mark.parametrize(
    "protected_user",
    [
        "root",
        "ROOT",
        "bin",
        "daemon",
        "sys",
        "sync",
        "games",
        "man",
        "lp",
        "mail",
        "nobody",
    ],
)
def test_adversarial_rotation_protected_system_accounts_rejected(
    auth_context, test_keypair, mock_validator, protected_user
):
    """Test rotation is refused fail-closed for any protected system account."""
    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": protected_user},
    )

    with pytest.raises(
        TargetAuthorizationError, match="Cannot rotate credentials for protected"
    ):
        executor.rotate_credential(req, test_keypair[0].encode("utf-8"))


def test_credential_non_disclosure_during_rotation(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test that private key material is NEVER leaked in logs, audit records, or exceptions."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    mock_audit = MagicMock(spec=ExecutionAuditService)

    # Mock SSH connection to simulate successful rotation
    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_stdout = MagicMock()
    mock_stdout.read.return_value = b"INSTALL_SUCCESS"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""

    connect_calls = 0

    def fake_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 4:
            # Connect 4 is Step 5 (old key revocation verification) -> must fail authentication
            raise paramiko.AuthenticationException("Permission denied (publickey)")
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

    mock_client.connect.side_effect = fake_connect
    mock_client.exec_command.side_effect = fake_exec_command
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(
        audit_service=mock_audit, network_validator=mock_validator
    )
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "10.0.0.1", "port": 22, "username": "opsforge-svc"},
    )

    old_priv_pem = test_keypair[0]
    res = executor.rotate_credential(req, old_priv_pem.encode("utf-8"))

    assert res.status == ExecutionStatus.SUCCESS
    assert res.new_secret_version is not None
    new_priv_pem = res.new_secret_version.decode("utf-8")

    # Verify log output does not contain private key material
    log_text = log_capture.getvalue()
    assert "BEGIN OPENSSH PRIVATE KEY" not in log_text
    assert old_priv_pem not in log_text
    assert new_priv_pem not in log_text

    # Verify audit record does not contain private key material
    if mock_audit.record_execution_event.called:
        call_args = mock_audit.record_execution_event.call_args[0]
        audit_res = call_args[1]
        safe_dict = audit_res.to_safe_dict()
        safe_str = str(safe_dict)
        assert "BEGIN OPENSSH PRIVATE KEY" not in safe_str
        assert old_priv_pem not in safe_str
        assert new_priv_pem not in safe_str


def test_ssh_target_executor_execute_adapter(
    auth_context, test_keypair, mock_validator, monkeypatch
):
    """Test legacy/worker execute adapter invokes rotate_credential and returns dict."""
    mock_client = MagicMock(spec=paramiko.SSHClient)
    connect_calls = 0

    def fake_connect(*args, **kwargs):
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls == 4:
            raise paramiko.AuthenticationException("Permission denied")
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

    mock_client.connect.side_effect = fake_connect
    mock_client.exec_command.side_effect = fake_exec_command
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    # Provide a resource resolver that returns host/port
    mock_resource = MagicMock()
    mock_resource.hostname_ip = "10.0.0.1"
    mock_resource.port = 22

    executor = SSHTargetExecutor(
        resource_resolver=lambda rid: mock_resource,
        network_validator=mock_validator,
    )
    dict_res = executor.execute(
        auth_context.resource_id, test_keypair[0].encode("utf-8")
    )

    assert dict_res["status"] == "success"
    assert dict_res["error"] is None
    assert dict_res["new_secret_version"] is not None
    assert b"BEGIN OPENSSH PRIVATE KEY" in dict_res["new_secret_version"]
