"""Unit tests for SSH Target Executor and SSH Connection Context."""

import io
import socket
import threading
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
    VerificationStatus,
)
from app.execution.exceptions import (
    ExecutionTimeoutError,
    InvalidExecutionContextError,
    TargetAuthenticationError,
    TransportError,
)
from app.execution.host_identity import (
    HostKeyMismatchError,
    HostKeyVerifier,
    UntrustedHostError,
)
from app.execution.network_validator import (
    TargetAddressValidationError,
    TargetAddressValidator,
    ValidatedTargetDestination,
)
from app.execution.ssh_executor import (
    SSHConnectionContext,
    SSHExecutionConfig,
    SSHTargetExecutor,
    _OpsForgeMissingHostKeyPolicy,
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


def test_ssh_execution_config_defaults():
    config = SSHExecutionConfig()
    assert config.connect_timeout == 10.0
    assert config.banner_timeout == 10.0
    assert config.auth_timeout == 10.0
    assert config.max_concurrent_connections == 10
    assert config.allow_loopback is False
    assert 22 in config.allowed_ports


def test_ssh_missing_host_key_policy():
    verifier = HostKeyVerifier()
    mock_audit = MagicMock(spec=ExecutionAuditService)
    policy = _OpsForgeMissingHostKeyPolicy(
        verifier=verifier,
        auto_trust=False,
        audit_service=mock_audit,
        resource_id=uuid4(),
        execution_id=uuid4(),
    )

    mock_key = MagicMock(spec=paramiko.PKey)
    mock_key.get_name.return_value = "ssh-ed25519"
    mock_key.asbytes.return_value = b"fake-key-bytes-1234567890123456"

    # 1. Untrusted host rejection
    with pytest.raises(UntrustedHostError, match="Untrusted target host"):
        policy.missing_host_key(MagicMock(), "target.example.com", mock_key)

    # 2. Auto-trust on first use
    policy_auto = _OpsForgeMissingHostKeyPolicy(
        verifier=verifier,
        auto_trust=True,
        audit_service=mock_audit,
        resource_id=uuid4(),
        execution_id=uuid4(),
    )
    policy_auto.missing_host_key(MagicMock(), "target.example.com", mock_key)
    assert verifier.get_trusted_key("target.example.com") is not None

    # 3. Matching key succeeds
    policy.missing_host_key(MagicMock(), "target.example.com", mock_key)

    # 4. Mismatched key fails
    bad_key = MagicMock(spec=paramiko.PKey)
    bad_key.get_name.return_value = "ssh-ed25519"
    bad_key.asbytes.return_value = b"different-bytes-1234567890123456"

    with pytest.raises(HostKeyMismatchError, match="HOST KEY MISMATCH DETECTED"):
        policy.missing_host_key(MagicMock(), "target.example.com", bad_key)


def test_ssh_connection_context_resolve_once_and_connect(monkeypatch):
    mock_validator = MagicMock(spec=TargetAddressValidator)
    mock_validator.validate_destination.return_value = ValidatedTargetDestination(
        original_host="target.example.com",
        resolved_ip="198.51.100.10",
        port=22,
        is_ipv6=False,
    )

    mock_sock = MagicMock(spec=socket.socket)
    monkeypatch.setattr(socket, "create_connection", lambda dest, timeout: mock_sock)

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_transport = MagicMock()
    mock_transport.is_active.return_value = True
    mock_client.get_transport.return_value = mock_transport
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    verifier = HostKeyVerifier()
    config = SSHExecutionConfig()

    ctx = SSHConnectionContext(
        target_host="target.example.com",
        target_port=22,
        username="opsforge-svc",
        network_validator=mock_validator,
        host_key_verifier=verifier,
        config=config,
    )

    with ctx as client:
        assert client is mock_client
        mock_validator.validate_destination.assert_called_once_with(
            "target.example.com", 22
        )
        mock_client.connect.assert_called_once()

    # Verify socket and client are closed in __exit__
    mock_client.close.assert_called_once()
    mock_sock.close.assert_called_once()


def test_ssh_connection_context_concurrency_limit_timeout():
    sem = threading.Semaphore(0)  # No slots available
    config = SSHExecutionConfig(
        max_concurrent_connections=1, connection_pool_timeout=0.01
    )

    ctx = SSHConnectionContext(
        target_host="target.example.com",
        target_port=22,
        username="opsforge-svc",
        config=config,
        semaphore=sem,
    )

    with pytest.raises(ExecutionTimeoutError, match="Connection concurrency limit"):
        with ctx:
            pass


def test_ssh_connection_context_target_validation_error(monkeypatch):
    mock_validator = MagicMock(spec=TargetAddressValidator)
    mock_validator.validate_destination.side_effect = TargetAddressValidationError(
        "Blocked cloud metadata"
    )

    ctx = SSHConnectionContext(
        target_host="169.254.169.254",
        target_port=22,
        username="opsforge-svc",
        network_validator=mock_validator,
    )

    with pytest.raises(
        TransportError, match="Target address validation rejected destination"
    ):
        with ctx:
            pass


def test_ssh_connection_context_auth_failure(monkeypatch):
    mock_validator = MagicMock(spec=TargetAddressValidator)
    mock_validator.validate_destination.return_value = ValidatedTargetDestination(
        original_host="target.example.com",
        resolved_ip="198.51.100.10",
        port=22,
        is_ipv6=False,
    )

    mock_sock = MagicMock(spec=socket.socket)
    monkeypatch.setattr(socket, "create_connection", lambda dest, timeout: mock_sock)

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_client.connect.side_effect = paramiko.AuthenticationException(
        "Permission denied (publickey)"
    )
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    ctx = SSHConnectionContext(
        target_host="target.example.com",
        target_port=22,
        username="opsforge-svc",
        network_validator=mock_validator,
    )

    with pytest.raises(TargetAuthenticationError, match="SSH authentication failed"):
        with ctx:
            pass

    mock_sock.close.assert_called_once()


def test_ssh_connection_context_load_private_keys():
    # Generate temporary RSA key for test
    rsa_key = paramiko.RSAKey.generate(2048)
    out = io.StringIO()
    rsa_key.write_private_key(out)
    pem_str = out.getvalue()

    loaded = SSHConnectionContext._load_private_key(pem_str)
    assert isinstance(loaded, paramiko.RSAKey)

    # Test invalid key raises TargetAuthenticationError
    with pytest.raises(
        TargetAuthenticationError, match="Failed to parse private key material"
    ):
        SSHConnectionContext._load_private_key("invalid-private-key-data")


def test_ssh_target_executor_can_execute():
    executor = SSHTargetExecutor()
    rid = uuid4()
    assert executor.can_execute(rid, ExecutionOperation.VALIDATE_TARGET) is True
    assert executor.can_execute(rid, ExecutionOperation.ROTATE_CREDENTIAL) is True
    assert executor.can_execute(rid, ExecutionOperation.PROVISION_ACCOUNT) is True
    assert executor.can_execute(rid, ExecutionOperation.REMOVE_ACCOUNT) is True
    # Future phase operations return False in Phase 6
    assert executor.can_execute(rid, ExecutionOperation.APPLY_JIT_GRANT) is False
    assert executor.can_execute(rid, ExecutionOperation.REVOKE_JIT_GRANT) is False


def test_ssh_target_executor_validate_target_success(auth_context, monkeypatch):
    mock_validator = MagicMock(spec=TargetAddressValidator)
    mock_validator.validate_destination.return_value = ValidatedTargetDestination(
        original_host="192.0.2.1",
        resolved_ip="192.0.2.1",
        port=22,
        is_ipv6=False,
    )

    mock_sock = MagicMock(spec=socket.socket)
    monkeypatch.setattr(socket, "create_connection", lambda dest, timeout: mock_sock)

    mock_client = MagicMock(spec=paramiko.SSHClient)
    mock_transport = MagicMock()
    mock_transport.is_active.return_value = True
    mock_client.get_transport.return_value = mock_transport
    monkeypatch.setattr(paramiko, "SSHClient", lambda: mock_client)

    executor = SSHTargetExecutor(network_validator=mock_validator)
    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "192.0.2.1", "port": 22, "username": "opsforge-svc"},
    )

    res = executor.validate_target(req)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert res.is_success is True


def test_ssh_target_executor_validate_target_missing_host(auth_context):
    executor = SSHTargetExecutor()
    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={},
    )

    with pytest.raises(
        InvalidExecutionContextError, match="Missing target hostname or IP"
    ):
        executor.validate_target(req)


def test_ssh_target_executor_phase_boundary_methods(auth_context):
    executor = SSHTargetExecutor()
    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
    )

    with pytest.raises(NotImplementedError, match="Phase 7"):
        executor.apply_jit_grant(req)

    with pytest.raises(NotImplementedError, match="Phase 8"):
        executor.revoke_jit_grant(req)
