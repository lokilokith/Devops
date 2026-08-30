"""Live integration tests for real SSH credential rotation against opsforge-disposable-target."""

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
from app.execution.exceptions import TargetAuthenticationError
from app.execution.host_identity import HostKeyVerifier
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
def initial_svc_key():
    with open(SVC_KEY_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_real_ssh_bootstrap_rotation_lifecycle(
    target_container, auth_context, trusted_verifier, initial_svc_key
):
    """Test full Add -> Verify -> Remove -> Verify cycle on real disposable target."""
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

    # 1. Verify initial working access with initial key
    with SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username="opsforge-svc",
        private_key_pem=initial_svc_key,
        network_validator=validator,
        host_key_verifier=trusted_verifier,
        config=config,
    ) as client:
        _, stdout, _ = client.exec_command("whoami")
        assert stdout.read().decode().strip() == "opsforge-svc"

    # 2. Execute credential rotation
    req = ExecutionRequest(
        operation=ExecutionOperation.ROTATE_CREDENTIAL,
        resource_id=auth_context.resource_id,
        authorization_context=auth_context,
        parameters={
            "host": TARGET_HOST,
            "port": TARGET_PORT,
            "username": "opsforge-svc",
        },
    )

    res = executor.rotate_credential(req, initial_svc_key.encode("utf-8"))
    assert res.status == ExecutionStatus.SUCCESS
    assert res.verification_status == VerificationStatus.VERIFIED_SUCCESS
    assert res.is_success is True
    assert res.new_secret_version is not None

    new_key_pem = res.new_secret_version.decode("utf-8")

    try:
        # 3. Verify OLD key is rejected
        with pytest.raises(
            TargetAuthenticationError, match="SSH authentication failed"
        ):
            with SSHConnectionContext(
                target_host=TARGET_HOST,
                target_port=TARGET_PORT,
                username="opsforge-svc",
                private_key_pem=initial_svc_key,
                network_validator=validator,
                host_key_verifier=trusted_verifier,
                config=config,
            ):
                pass

        # 4. Verify NEW key continues to work
        with SSHConnectionContext(
            target_host=TARGET_HOST,
            target_port=TARGET_PORT,
            username="opsforge-svc",
            private_key_pem=new_key_pem,
            network_validator=validator,
            host_key_verifier=trusted_verifier,
            config=config,
        ) as client:
            _, stdout, _ = client.exec_command("whoami")
            assert stdout.read().decode().strip() == "opsforge-svc"

    finally:
        # Restore initial test key so other tests and future runs remain functional
        with open(SVC_KEY_PATH + ".pub", "r", encoding="utf-8") as f:
            std_pub = f.read().strip()
        for key_to_try in [new_key_pem, initial_svc_key]:
            if not key_to_try:
                continue
            try:
                with SSHConnectionContext(
                    target_host=TARGET_HOST,
                    target_port=TARGET_PORT,
                    username="opsforge-svc",
                    private_key_pem=key_to_try,
                    network_validator=validator,
                    host_key_verifier=trusted_verifier,
                    config=config,
                ) as client:
                    client.exec_command(f'echo "{std_pub}" > ~/.ssh/authorized_keys')
                    break
            except Exception:
                pass


def test_three_sequential_real_rotations(
    target_container, auth_context, trusted_verifier, initial_svc_key
):
    """Test 3 consecutive rotations to prove the rotation mechanism does not work only once."""
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

    current_key_pem = initial_svc_key

    try:
        for i in range(1, 4):
            req = ExecutionRequest(
                operation=ExecutionOperation.ROTATE_CREDENTIAL,
                resource_id=auth_context.resource_id,
                authorization_context=auth_context,
                parameters={
                    "host": TARGET_HOST,
                    "port": TARGET_PORT,
                    "username": "opsforge-svc",
                },
            )
            res = executor.rotate_credential(req, current_key_pem.encode("utf-8"))
            assert (
                res.status == ExecutionStatus.SUCCESS
            ), f"Rotation {i} failed: {res.error_message}"
            assert res.verification_status == VerificationStatus.VERIFIED_SUCCESS
            assert res.new_secret_version is not None

            # Verify old key fails
            with pytest.raises(TargetAuthenticationError):
                with SSHConnectionContext(
                    target_host=TARGET_HOST,
                    target_port=TARGET_PORT,
                    username="opsforge-svc",
                    private_key_pem=current_key_pem,
                    network_validator=validator,
                    host_key_verifier=trusted_verifier,
                    config=config,
                ):
                    pass

            # Update current key to new key
            current_key_pem = res.new_secret_version.decode("utf-8")

            # Verify new key works
            with SSHConnectionContext(
                target_host=TARGET_HOST,
                target_port=TARGET_PORT,
                username="opsforge-svc",
                private_key_pem=current_key_pem,
                network_validator=validator,
                host_key_verifier=trusted_verifier,
                config=config,
            ) as client:
                _, stdout, _ = client.exec_command("whoami")
                assert stdout.read().decode().strip() == "opsforge-svc"

    finally:
        # Restore standard initial key in target container
        with open(SVC_KEY_PATH + ".pub", "r", encoding="utf-8") as f:
            std_pub = f.read().strip()
        for key_to_try in [current_key_pem, initial_svc_key]:
            if not key_to_try:
                continue
            try:
                with SSHConnectionContext(
                    target_host=TARGET_HOST,
                    target_port=TARGET_PORT,
                    username="opsforge-svc",
                    private_key_pem=key_to_try,
                    network_validator=validator,
                    host_key_verifier=trusted_verifier,
                    config=config,
                ) as client:
                    client.exec_command(f'echo "{std_pub}" > ~/.ssh/authorized_keys')
                    break
            except Exception:
                pass
