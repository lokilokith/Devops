"""Integration tests for SSHTargetExecutor and SSHConnectionContext against real disposable target."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
    VerificationStatus,
)
from app.execution.exceptions import (
    TargetAuthenticationError,
)
from app.execution.host_identity import (
    HostKeyMismatchError,
    HostKeyVerifier,
    UntrustedHostError,
)
from app.execution.network_validator import TargetAddressValidator
from app.execution.ssh_executor import (
    SSHConnectionContext,
    SSHExecutionConfig,
    SSHTargetExecutor,
)
from tests.execution.test_target_bootstrap import (
    HOST_ED25519_PUB_PATH,
    SVC_KEY_PATH,
    TARGET_HOST,
    TARGET_PORT,
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


@pytest.fixture
def trusted_verifier():
    with open(HOST_ED25519_PUB_PATH, "r", encoding="utf-8") as f:
        host_pub_line = f.read().strip()
    key_type, key_b64 = host_pub_line.split()[:2]
    verifier = HostKeyVerifier()
    verifier.register_trusted_key(TARGET_HOST, key_type, key_b64)
    return verifier


@pytest.fixture
def svc_private_key():
    with open(SVC_KEY_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_ssh_connection_context_real_target_success(
    target_container, trusted_verifier, svc_private_key
):
    """Test real SSH connection and host key verification against disposable target."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )

    ctx = SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username="opsforge-svc",
        private_key_pem=svc_private_key,
        network_validator=validator,
        host_key_verifier=trusted_verifier,
        config=config,
    )

    with ctx as client:
        transport = client.get_transport()
        assert transport is not None
        assert transport.is_active()

        # Run simple non-destructive command
        stdin, stdout, stderr = client.exec_command("whoami")
        assert stdout.read().decode().strip() == "opsforge-svc"

    # Context exited - verify clean disconnect
    assert transport.is_active() is False


def test_ssh_connection_context_untrusted_host_rejection(
    target_container, svc_private_key
):
    """Test connection is rejected fail-closed when host is not in trusted verifier."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    empty_verifier = HostKeyVerifier()  # No trusted keys registered
    config = SSHExecutionConfig(
        allow_loopback=True,
        allowed_ports={22, TARGET_PORT},
        auto_trust_on_first_use=False,
    )
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )

    ctx = SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username="opsforge-svc",
        private_key_pem=svc_private_key,
        network_validator=validator,
        host_key_verifier=empty_verifier,
        config=config,
    )

    with pytest.raises(UntrustedHostError, match="Untrusted target host"):
        with ctx:
            pass


def test_ssh_connection_context_host_key_mismatch_hard_fail(
    target_container, svc_private_key
):
    """Test connection hard fails when target host key does not match pinned key."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    mismatched_verifier = HostKeyVerifier()
    # Register wrong key data
    fake_b64 = "AAAAC3NzaC1lZDI1NTE5AAAAIG5vdEFSZWFsSG9zdEtleURhdGExMjM0NTY3ODkwMTI="
    mismatched_verifier.register_trusted_key(TARGET_HOST, "ssh-ed25519", fake_b64)

    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )

    ctx = SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username="opsforge-svc",
        private_key_pem=svc_private_key,
        network_validator=validator,
        host_key_verifier=mismatched_verifier,
        config=config,
    )

    with pytest.raises(HostKeyMismatchError, match="HOST KEY MISMATCH DETECTED"):
        with ctx:
            pass


def test_ssh_connection_context_invalid_credentials_fail(
    target_container, trusted_verifier
):
    """Test connection fails with TargetAuthenticationError on bad key."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    # Generate an un-authorized RSA key
    import io

    import paramiko

    rsa_key = paramiko.RSAKey.generate(2048)
    out = io.StringIO()
    rsa_key.write_private_key(out)
    unauth_key_pem = out.getvalue()

    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )

    ctx = SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username="opsforge-svc",
        private_key_pem=unauth_key_pem,
        network_validator=validator,
        host_key_verifier=trusted_verifier,
        config=config,
    )

    with pytest.raises(TargetAuthenticationError, match="SSH authentication failed"):
        with ctx:
            pass


def test_ssh_target_executor_validate_target_real(
    target_container, auth_context, trusted_verifier, svc_private_key
):
    """Test SSHTargetExecutor.validate_target end-to-end against live disposable target."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )

    executor = SSHTargetExecutor(
        config=config,
        network_validator=validator,
        host_key_verifier=trusted_verifier,
    )

    req = ExecutionRequest(
        operation=ExecutionOperation.VALIDATE_TARGET,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={
            "host": TARGET_HOST,
            "port": TARGET_PORT,
            "username": "opsforge-svc",
            "private_key": svc_private_key,
        },
    )

    res = executor.validate_target(req)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert res.is_success is True
    assert res.details["status"] == "connected_and_verified"
