"""Unit tests for SSHTargetExecutor.provision_account and remove_account."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
    FailureClassification,
    VerificationStatus,
)
from app.execution.ssh_executor import SSHTargetExecutor
from app.vault.ssh_keys import generate_ed25519_keypair


def _create_request(op=ExecutionOperation.PROVISION_ACCOUNT):
    from datetime import datetime, timedelta, timezone

    now_dt = datetime.now(timezone.utc)
    auth_ctx = ExecutionAuthorizationContext(
        user_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        target_account_binding_id=uuid.uuid4(),
        credential_id=uuid.uuid4(),
        requested_at=now_dt,
        expires_at=now_dt + timedelta(minutes=15),
    )
    priv_pem, pub_ssh = generate_ed25519_keypair()
    return (
        ExecutionRequest(
            operation=op,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": "127.0.0.1",
                "port": 22,
                "target_os_username": "test_user",
                "public_key": pub_ssh,
                "bootstrap_credential": priv_pem.encode("utf-8"),
                "user_private_key": priv_pem.encode("utf-8"),
            },
        ),
        priv_pem,
        pub_ssh,
    )


def _mock_channel(exit_status=0):
    chan = MagicMock()
    chan.recv_exit_status.return_value = exit_status
    return chan


def test_ssh_executor_provision_account_success():
    """Test SSHTargetExecutor.provision_account successful execution and verification."""
    executor = SSHTargetExecutor()
    req, priv_pem, pub_ssh = _create_request()

    mock_client = MagicMock()

    # Mock bootstrap command (helper provision_account)
    stdout_bootstrap = MagicMock()
    stdout_bootstrap.read.return_value = b"SUCCESS: provision_account test_user\n"
    stdout_bootstrap.channel = _mock_channel(0)
    stderr_bootstrap = MagicMock()
    stderr_bootstrap.read.return_value = b""

    # Mock user verification commands (whoami, echo $SHELL, sudo -n true)
    stdout_whoami = MagicMock()
    stdout_whoami.read.return_value = b"test_user\n"
    stdout_whoami.channel = _mock_channel(0)

    stdout_shell = MagicMock()
    stdout_shell.read.return_value = b"/bin/bash\n"
    stdout_shell.channel = _mock_channel(0)

    stdout_sudo = MagicMock()
    stdout_sudo.read.return_value = b""
    stdout_sudo.channel = _mock_channel(1)  # sudo -n true must fail (exit 1)

    mock_client.exec_command.side_effect = [
        (MagicMock(), stdout_bootstrap, stderr_bootstrap),
        (MagicMock(), stdout_whoami, MagicMock()),
        (MagicMock(), stdout_shell, MagicMock()),
        (MagicMock(), stdout_sudo, MagicMock()),
    ]

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        result = executor.provision_account(req)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert result.details["target_os_username"] == "test_user"


def test_ssh_executor_provision_account_helper_failure():
    """Test helper execution failure mapping."""
    executor = SSHTargetExecutor()
    req, priv_pem, pub_ssh = _create_request()

    mock_client = MagicMock()
    stdout_bootstrap = MagicMock()
    stdout_bootstrap.read.return_value = b""
    stdout_bootstrap.channel = _mock_channel(1)
    stderr_bootstrap = MagicMock()
    stderr_bootstrap.read.return_value = b"Account name is invalid"

    mock_client.exec_command.return_value = (
        MagicMock(),
        stdout_bootstrap,
        stderr_bootstrap,
    )

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        result = executor.provision_account(req)

    assert result.status == ExecutionStatus.FAILED
    assert result.failure_classification == FailureClassification.TARGET_FAILURE


def test_ssh_executor_remove_account_success():
    """Test SSHTargetExecutor.remove_account success and verification."""
    executor = SSHTargetExecutor()
    req, priv_pem, pub_ssh = _create_request(ExecutionOperation.REMOVE_ACCOUNT)

    mock_client = MagicMock()

    stdout_remove = MagicMock()
    stdout_remove.read.return_value = b"SUCCESS: remove_account test_user\n"
    stdout_remove.channel = _mock_channel(0)

    stdout_verify = MagicMock()
    stdout_verify.read.return_value = b""
    stdout_verify.channel = _mock_channel(1)  # id test_user must fail (exit 1)

    mock_client.exec_command.side_effect = [
        (MagicMock(), stdout_remove, MagicMock()),
        (MagicMock(), stdout_verify, MagicMock()),
    ]

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        result = executor.remove_account(req)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.verification_status == VerificationStatus.VERIFIED_SUCCESS


def test_ssh_executor_phase_boundary_methods():
    """Test Phase 7 and Phase 8 methods raise NotImplementedError in Phase 6."""
    executor = SSHTargetExecutor()
    req, _, _ = _create_request()

    with pytest.raises(NotImplementedError, match="Phase 7"):
        executor.apply_jit_grant(req)

    with pytest.raises(NotImplementedError, match="Phase 8"):
        executor.revoke_jit_grant(req)
