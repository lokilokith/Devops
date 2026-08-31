"""Unit tests for SSH Target Executor JIT privilege elevation and revocation operations."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
    VerificationStatus,
)
from app.execution.ssh_executor import SSHTargetExecutor


@pytest.fixture
def ssh_executor():
    return SSHTargetExecutor()


def create_auth_context(user_id=None, resource_id=None, grant_id=None, binding_id=None):
    now = datetime.now(timezone.utc)
    return ExecutionAuthorizationContext(
        user_id=user_id or uuid.uuid4(),
        resource_id=resource_id or uuid.uuid4(),
        credential_id=uuid.uuid4(),
        target_account_binding_id=binding_id or uuid.uuid4(),
        grant_id=grant_id or uuid.uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )


def test_apply_jit_grant_success(ssh_executor):
    """Verify apply_jit_grant invokes helper and verifies live sudo privilege."""
    grant_id = uuid.uuid4()
    res_id = uuid.uuid4()
    auth_ctx = create_auth_context(resource_id=res_id, grant_id=grant_id)

    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=res_id,
        authorization_context=auth_ctx,
        parameters={
            "host": "127.0.0.1",
            "port": 22,
            "grant_id": str(grant_id),
            "target_os_username": "target_user",
            "command_set_id": "system_health_check",
            "bootstrap_credential": b"dummy_key",
        },
    )

    mock_client = MagicMock()
    mock_stdout_add = MagicMock()
    mock_stdout_add.channel.recv_exit_status.return_value = 0

    mock_stdout_verify = MagicMock()
    mock_stdout_verify.channel.recv_exit_status.return_value = 0
    mock_stdout_verify.read.return_value = b"(root) NOPASSWD: /usr/bin/uptime\n"

    # Sequence of exec_command calls: 1) add_jit_grant, 2) sudo -l
    mock_client.exec_command.side_effect = [
        (MagicMock(), mock_stdout_add, MagicMock(read=lambda: b"")),
        (MagicMock(), mock_stdout_verify, MagicMock(read=lambda: b"")),
    ]

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        result = ssh_executor.apply_jit_grant(req)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert result.details["verified"] is True
    assert result.details["command_set_id"] == "system_health_check"


def test_revoke_jit_grant_success(ssh_executor):
    """Verify revoke_jit_grant invokes remove_jit_grant and verifies file removal."""
    grant_id = uuid.uuid4()
    res_id = uuid.uuid4()
    auth_ctx = create_auth_context(resource_id=res_id, grant_id=grant_id)

    req = ExecutionRequest(
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        resource_id=res_id,
        authorization_context=auth_ctx,
        parameters={
            "host": "127.0.0.1",
            "port": 22,
            "grant_id": str(grant_id),
            "bootstrap_credential": b"dummy_key",
        },
    )

    mock_client = MagicMock()
    mock_stdout_rm = MagicMock()
    mock_stdout_rm.channel.recv_exit_status.return_value = 0

    # Verification: test -f returns non-zero (file gone)
    mock_stdout_chk = MagicMock()
    mock_stdout_chk.channel.recv_exit_status.return_value = 1

    mock_client.exec_command.side_effect = [
        (MagicMock(), mock_stdout_rm, MagicMock(read=lambda: b"")),
        (MagicMock(), mock_stdout_chk, MagicMock(read=lambda: b"")),
    ]

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        result = ssh_executor.revoke_jit_grant(req)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert result.details["revoked"] is True
