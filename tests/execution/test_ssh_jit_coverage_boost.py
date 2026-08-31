"""Coverage boost for SSHTargetExecutor apply_jit_grant and revoke_jit_grant branches."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
    FailureClassification,
)
from app.execution.ssh_executor import SSHTargetExecutor


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


def test_apply_jit_grant_missing_params():
    executor = SSHTargetExecutor()
    auth_ctx = create_auth_context()
    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "host": "198.51.100.1"
        },  # missing username, grant_id, command_set_id
    )
    res = executor.apply_jit_grant(req)
    assert res.status == ExecutionStatus.FAILED
    assert res.failure_classification == FailureClassification.CONFIGURATION_FAILURE


def test_apply_jit_grant_helper_nonzero_exit():
    mock_audit = MagicMock()
    executor = SSHTargetExecutor(audit_service=mock_audit)
    grant_id = uuid.uuid4()
    auth_ctx = create_auth_context(grant_id=grant_id)

    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "host": "198.51.100.1",
            "port": 22,
            "grant_id": str(grant_id),
            "target_os_username": "target_user",
            "command_set_id": "system_health_check",
            "bootstrap_credential": b"dummy",
        },
    )

    mock_client = MagicMock()
    mock_stdout_add = MagicMock()
    mock_stdout_add.channel.recv_exit_status.return_value = 1
    mock_stderr_add = MagicMock(
        read=lambda: b"opsforge-helper: visudo syntax check failed"
    )
    mock_client.exec_command.return_value = (
        MagicMock(),
        mock_stdout_add,
        mock_stderr_add,
    )

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        res = executor.apply_jit_grant(req)

    assert res.status == ExecutionStatus.FAILED
    assert "visudo" in (res.error_message or "").lower()
    mock_audit.record_execution_event.assert_called_once()


def test_apply_jit_grant_verification_failure_uncertain():
    mock_audit = MagicMock()
    executor = SSHTargetExecutor(audit_service=mock_audit)
    grant_id = uuid.uuid4()
    auth_ctx = create_auth_context(grant_id=grant_id)

    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "host": "198.51.100.1",
            "port": 22,
            "grant_id": str(grant_id),
            "target_os_username": "target_user",
            "command_set_id": "system_health_check",
            "bootstrap_credential": b"dummy",
        },
    )

    mock_client = MagicMock()
    # 1: helper add succeeds
    mock_stdout_add = MagicMock()
    mock_stdout_add.channel.recv_exit_status.return_value = 0
    # 2: sudo -l fails
    mock_stdout_verify = MagicMock()
    mock_stdout_verify.channel.recv_exit_status.return_value = 1
    # 3: test -f check fails
    mock_stdout_chk = MagicMock()
    mock_stdout_chk.channel.recv_exit_status.return_value = 1

    mock_client.exec_command.side_effect = [
        (MagicMock(), mock_stdout_add, MagicMock(read=lambda: b"")),
        (MagicMock(), mock_stdout_verify, MagicMock(read=lambda: b"not allowed")),
        (MagicMock(), mock_stdout_chk, MagicMock(read=lambda: b"")),
    ]

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        res = executor.apply_jit_grant(req)

    assert res.status == ExecutionStatus.FAILED
    assert res.failure_classification == FailureClassification.UNCERTAIN_STATE


def test_apply_jit_grant_connection_exception():
    executor = SSHTargetExecutor()
    grant_id = uuid.uuid4()
    auth_ctx = create_auth_context(grant_id=grant_id)

    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "host": "198.51.100.1",
            "port": 22,
            "grant_id": str(grant_id),
            "target_os_username": "target_user",
            "command_set_id": "system_health_check",
            "bootstrap_credential": b"dummy",
        },
    )

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.side_effect = ConnectionResetError("SSH socket disconnected")
        res = executor.apply_jit_grant(req)

    assert res.status == ExecutionStatus.FAILED
    assert res.failure_classification == FailureClassification.TARGET_FAILURE


def test_revoke_jit_grant_helper_nonzero_exit():
    mock_audit = MagicMock()
    executor = SSHTargetExecutor(audit_service=mock_audit)
    grant_id = uuid.uuid4()
    auth_ctx = create_auth_context(grant_id=grant_id)

    req = ExecutionRequest(
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "host": "198.51.100.1",
            "port": 22,
            "grant_id": str(grant_id),
            "bootstrap_credential": b"dummy",
        },
    )

    mock_client = MagicMock()
    mock_stdout_rm = MagicMock()
    mock_stdout_rm.channel.recv_exit_status.return_value = 1
    mock_stderr_rm = MagicMock(read=lambda: b"opsforge-helper: drop-in removal failed")
    mock_client.exec_command.return_value = (
        MagicMock(),
        mock_stdout_rm,
        mock_stderr_rm,
    )

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        res = executor.revoke_jit_grant(req)

    assert res.status == ExecutionStatus.FAILED
    mock_audit.record_execution_event.assert_called_once()


def test_revoke_jit_grant_verification_file_still_exists():
    executor = SSHTargetExecutor()
    grant_id = uuid.uuid4()
    auth_ctx = create_auth_context(grant_id=grant_id)

    req = ExecutionRequest(
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "host": "198.51.100.1",
            "port": 22,
            "grant_id": str(grant_id),
            "bootstrap_credential": b"dummy",
        },
    )

    mock_client = MagicMock()
    # 1: remove succeeds
    mock_stdout_rm = MagicMock()
    mock_stdout_rm.channel.recv_exit_status.return_value = 0
    # 2: test -f check succeeds (0 means file still exists! error!)
    mock_stdout_chk = MagicMock()
    mock_stdout_chk.channel.recv_exit_status.return_value = 0

    mock_client.exec_command.side_effect = [
        (MagicMock(), mock_stdout_rm, MagicMock(read=lambda: b"")),
        (MagicMock(), mock_stdout_chk, MagicMock(read=lambda: b"")),
    ]

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        res = executor.revoke_jit_grant(req)

    assert res.status == ExecutionStatus.FAILED
    assert "still exists" in (res.error_message or "").lower()


def test_revoke_jit_grant_missing_params():
    executor = SSHTargetExecutor()
    auth_ctx = create_auth_context()
    req = ExecutionRequest(
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={},
    )
    res = executor.revoke_jit_grant(req)
    assert res.status == ExecutionStatus.FAILED
    assert res.failure_classification == FailureClassification.CONFIGURATION_FAILURE


def test_ssh_jit_resource_resolver_branches():
    import base64

    b64_key = base64.b64encode(b"0" * 32).decode()
    mock_res = MagicMock()
    mock_res.hostname_ip = "198.51.100.2"
    mock_res.port = 22
    mock_res.pinned_host_key = f"ssh-ed25519 {b64_key}"

    executor = SSHTargetExecutor(resource_resolver=lambda rid: mock_res)
    grant_id = uuid.uuid4()
    auth_ctx = create_auth_context(grant_id=grant_id)

    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "grant_id": str(grant_id),
            "target_os_username": "target_user",
            "command_set_id": "system_health_check",
            "bootstrap_credential": b"dummy",
        },
    )

    mock_client = MagicMock()
    mock_stdout_add = MagicMock()
    mock_stdout_add.channel.recv_exit_status.return_value = 0
    mock_stdout_verify = MagicMock()
    mock_stdout_verify.channel.recv_exit_status.return_value = 0
    mock_stdout_verify.read.return_value = b"(root) NOPASSWD: /usr/bin/uptime\n"

    mock_client.exec_command.side_effect = [
        (MagicMock(), mock_stdout_add, MagicMock(read=lambda: b"")),
        (MagicMock(), mock_stdout_verify, MagicMock(read=lambda: b"")),
    ]

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        res = executor.apply_jit_grant(req)

    assert res.status == ExecutionStatus.SUCCESS

    # Also test revoke with resource resolver
    req_rev = ExecutionRequest(
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "grant_id": str(grant_id),
            "bootstrap_credential": b"dummy",
        },
    )

    mock_stdout_rm = MagicMock()
    mock_stdout_rm.channel.recv_exit_status.return_value = 0
    mock_stdout_chk = MagicMock()
    mock_stdout_chk.channel.recv_exit_status.return_value = 1

    mock_client.exec_command.side_effect = [
        (MagicMock(), mock_stdout_rm, MagicMock(read=lambda: b"")),
        (MagicMock(), mock_stdout_chk, MagicMock(read=lambda: b"")),
    ]

    with patch("app.execution.ssh_executor.SSHConnectionContext") as mock_conn:
        mock_conn.return_value.__enter__.return_value = mock_client
        res_rev = executor.revoke_jit_grant(req_rev)

    assert res_rev.status == ExecutionStatus.SUCCESS
