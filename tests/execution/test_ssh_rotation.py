from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    RotationStep,
)
from app.execution.exceptions import (
    InvalidExecutionContextError,
    TargetAuthorizationError,
)
from app.execution.ssh_executor import SSHTargetExecutor
from app.vault.ssh_keys import (
    compute_key_fingerprint,
    extract_public_key,
    generate_ed25519_keypair,
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


def test_generate_ed25519_keypair_in_memory():
    """Test generating Ed25519 keypair in memory."""
    priv_pem, pub_ssh = generate_ed25519_keypair(comment="test-key")
    assert "BEGIN OPENSSH PRIVATE KEY" in priv_pem
    assert pub_ssh.startswith("ssh-ed25519 ")
    assert "test-key" in pub_ssh


def test_extract_public_key_and_fingerprint():
    """Test extracting public key and calculating SHA256 fingerprint from private PEM."""
    priv_pem, pub_ssh = generate_ed25519_keypair(comment="fp-test")
    extracted_pub = extract_public_key(priv_pem, comment="fp-test")
    assert extracted_pub.strip() == pub_ssh.strip()

    fp1 = compute_key_fingerprint(pub_ssh)
    fp2 = compute_key_fingerprint(priv_pem)
    assert fp1.startswith("SHA256:")
    assert fp1 == fp2


def test_extract_public_key_invalid_pem():
    """Test extracting public key from malformed PEM raises ValueError."""
    with pytest.raises(ValueError, match="Failed to load SSH private key"):
        extract_public_key("invalid-pem-content")


def test_compute_fingerprint_invalid():
    """Test computing fingerprint on empty string raises ValueError."""
    with pytest.raises(ValueError, match="Key material must be a non-empty string"):
        compute_key_fingerprint("")


def test_rotation_step_enum_members():
    """Verify all canonical rotation state machine steps exist."""
    assert RotationStep.PENDING.value == "PENDING"
    assert RotationStep.INSTALLING.value == "INSTALLING"
    assert RotationStep.NEW_CREDENTIAL_VERIFIED.value == "NEW_CREDENTIAL_VERIFIED"
    assert RotationStep.REMOVING_OLD.value == "REMOVING_OLD"
    assert RotationStep.OLD_CREDENTIAL_REVOKED.value == "OLD_CREDENTIAL_REVOKED"
    assert RotationStep.VERIFIED.value == "VERIFIED"
    assert RotationStep.COMPLETED.value == "COMPLETED"
    assert RotationStep.FAILED.value == "FAILED"
    assert RotationStep.RECOVERY_REQUIRED.value == "RECOVERY_REQUIRED"


def test_ssh_target_executor_can_execute_rotation():
    """Test SSHTargetExecutor reports True for ROTATE_CREDENTIAL in Phase 4."""
    executor = SSHTargetExecutor()
    rid = uuid4()
    assert executor.can_execute(rid, ExecutionOperation.VALIDATE_TARGET) is True
    assert executor.can_execute(rid, ExecutionOperation.ROTATE_CREDENTIAL) is True
    assert executor.can_execute(rid, ExecutionOperation.PROVISION_ACCOUNT) is True
    assert executor.can_execute(rid, ExecutionOperation.REMOVE_ACCOUNT) is True
    assert executor.can_execute(rid, ExecutionOperation.APPLY_JIT_GRANT) is False


def test_ssh_target_executor_rotate_credential_protected_account_rejected(auth_context):
    """Test attempting to rotate protected system accounts is rejected."""
    executor = SSHTargetExecutor()
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={"host": "127.0.0.1", "port": 22, "username": "root"},
    )
    with pytest.raises(
        TargetAuthorizationError, match="Cannot rotate credentials for protected"
    ):
        executor.rotate_credential(req, b"fake-secret")


def test_ssh_target_executor_rotate_credential_missing_host(auth_context):
    """Test missing host parameter raises InvalidExecutionContextError."""
    executor = SSHTargetExecutor()
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={},
    )
    with pytest.raises(
        InvalidExecutionContextError, match="Missing target hostname or IP"
    ):
        executor.rotate_credential(req, b"fake-secret")
