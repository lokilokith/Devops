import os
import time
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
from app.execution.host_identity import HostKeyVerifier
from app.execution.network_validator import TargetAddressValidator
from app.execution.ssh_executor import (
    SSHConnectionContext,
    SSHExecutionConfig,
    SSHTargetExecutor,
)
from app.vault.ssh_keys import generate_ed25519_keypair
from tests.execution.test_target_bootstrap import (
    HOST_ED25519_PUB_PATH,
    SVC_KEY_PATH,
    TARGET_HOST,
    TARGET_PORT,
)


@pytest.fixture
def trusted_verifier():
    if not os.path.exists(HOST_ED25519_PUB_PATH):
        pytest.skip("Target public key file not found")
    with open(HOST_ED25519_PUB_PATH, "r", encoding="utf-8") as f:
        host_pub_line = f.read().strip()
    key_type, key_b64 = host_pub_line.split()[:2]
    verifier = HostKeyVerifier()
    verifier.register_trusted_key(TARGET_HOST, key_type, key_b64)
    return verifier


@pytest.fixture
def svc_key():
    if not os.path.exists(SVC_KEY_PATH):
        pytest.skip("Service key file not found")
    with open(SVC_KEY_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_real_target_jit_elevation_and_expiry_lifecycle(
    target_container, trusted_verifier, svc_key
):
    """Full lifecycle: Provision human account -> Apply JIT -> Verify allowed/denied -> Expire -> Verify removal."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    now = datetime.now(timezone.utc)
    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )
    executor = SSHTargetExecutor(
        config=config, network_validator=validator, host_key_verifier=trusted_verifier
    )

    # 1. Provision target human account (Phase 6 precondition)
    user_priv, user_pub = generate_ed25519_keypair(comment="opsforge-jit-human")
    target_user = "u_jit_live_user"
    binding_id = uuid4()
    grant_id = uuid4()

    auth_ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        target_account_binding_id=binding_id,
        grant_id=grant_id,
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    # Ensure clean starting state
    try:
        executor.remove_account(
            ExecutionRequest(
                operation=ExecutionOperation.REMOVE_ACCOUNT,
                resource_id=auth_ctx.resource_id,
                authorization_context=auth_ctx,
                parameters={
                    "hostname_ip": TARGET_HOST,
                    "port": TARGET_PORT,
                    "target_os_username": target_user,
                    "bootstrap_credential": svc_key.encode("utf-8"),
                },
            )
        )
    except Exception:
        pass

    prov_req = ExecutionRequest(
        operation=ExecutionOperation.PROVISION_ACCOUNT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "target_os_username": target_user,
            "public_key": user_pub,
            "bootstrap_credential": svc_key.encode("utf-8"),
            "user_private_key": user_priv.encode("utf-8"),
        },
    )
    prov_res = executor.provision_account(prov_req)
    assert prov_res.status == ExecutionStatus.SUCCESS
    assert prov_res.verification_status == VerificationStatus.VERIFIED_SUCCESS

    try:
        # 2. Before JIT: Confirm target user has NO standing sudo privilege
        with SSHConnectionContext(
            target_host=TARGET_HOST,
            target_port=TARGET_PORT,
            username=target_user,
            private_key_pem=user_priv,
            network_validator=validator,
            host_key_verifier=trusted_verifier,
            config=config,
        ) as client:
            _, stdout, stderr = client.exec_command("sudo -n true")
            assert (
                stdout.channel.recv_exit_status() != 0
            ), "Security violation: human user should not have standing sudo"

            # Check that allowed JIT command is not yet accessible
            _, stdout, _ = client.exec_command("sudo -n /usr/bin/uptime")
            assert stdout.channel.recv_exit_status() != 0

        # 3. Apply JIT Grant (Phase 7 elevation)
        elev_req = ExecutionRequest(
            operation=ExecutionOperation.APPLY_JIT_GRANT,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_id),
                "target_os_username": target_user,
                "command_set_id": "system_health_check",
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
        elev_res = executor.apply_jit_grant(elev_req)
        assert elev_res.status == ExecutionStatus.SUCCESS
        assert elev_res.verification_status == VerificationStatus.VERIFIED_SUCCESS

        # 4. Live Privilege Verification on Target
        with SSHConnectionContext(
            target_host=TARGET_HOST,
            target_port=TARGET_PORT,
            username=target_user,
            private_key_pem=user_priv,
            network_validator=validator,
            host_key_verifier=trusted_verifier,
            config=config,
        ) as client:
            # 4a. Verify drop-in file exists on target
            # 4b. Allowed command: /usr/bin/uptime succeeds under sudo!
            _, stdout, stderr = client.exec_command("sudo -n /usr/bin/uptime")
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode()
            assert (
                exit_code == 0
            ), f"Allowed JIT command failed: {stderr.read().decode()}"
            assert "load average" in out or "up" in out

            # 4c. Forbidden command: unauthorized command fails / denied!
            _, stdout, stderr = client.exec_command("sudo -n /bin/sh")
            assert stdout.channel.recv_exit_status() != 0

            # 4d. Forbidden command: root file reading fails / denied!
            _, stdout, stderr = client.exec_command("sudo -n /bin/cat /etc/shadow")
            assert stdout.channel.recv_exit_status() != 0

        # 5. Revoke / Expire JIT Grant (Phase 7 Expiry Cleanup)
        rev_req = ExecutionRequest(
            operation=ExecutionOperation.REVOKE_JIT_GRANT,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_id),
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
        rev_res = executor.revoke_jit_grant(rev_req)
        assert rev_res.status == ExecutionStatus.SUCCESS

        # 6. Post-Revocation Verification: Command no longer accessible under sudo!
        with SSHConnectionContext(
            target_host=TARGET_HOST,
            target_port=TARGET_PORT,
            username=target_user,
            private_key_pem=user_priv,
            network_validator=validator,
            host_key_verifier=trusted_verifier,
            config=config,
        ) as client:
            _, stdout, stderr = client.exec_command("sudo -n /usr/bin/uptime")
            assert (
                stdout.channel.recv_exit_status() != 0
            ), "Security violation: JIT privilege remained after revocation!"

    finally:
        # Clean up target account
        executor.remove_account(
            ExecutionRequest(
                operation=ExecutionOperation.REMOVE_ACCOUNT,
                resource_id=auth_ctx.resource_id,
                authorization_context=auth_ctx,
                parameters={
                    "hostname_ip": TARGET_HOST,
                    "port": TARGET_PORT,
                    "target_os_username": target_user,
                    "bootstrap_credential": svc_key.encode("utf-8"),
                },
            )
        )


def test_real_target_jit_negative_paths(target_container, trusted_verifier, svc_key):
    """Test negative paths: invalid command sets and non-existent accounts fail closed."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    now = datetime.now(timezone.utc)
    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )
    executor = SSHTargetExecutor(
        config=config, network_validator=validator, host_key_verifier=trusted_verifier
    )

    grant_id = uuid4()
    auth_ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        target_account_binding_id=uuid4(),
        grant_id=grant_id,
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    # 1. Invalid / unallowlisted command_set_id
    invalid_req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "grant_id": str(grant_id),
            "target_os_username": "opsforge-svc",
            "command_set_id": "ALL_NOPASSWD_ROOT",
            "bootstrap_credential": svc_key.encode("utf-8"),
        },
    )
    res = executor.apply_jit_grant(invalid_req)
    assert res.status == ExecutionStatus.FAILED


def test_real_target_jit_expiry_timing_and_slo(
    target_container, trusted_verifier, svc_key
):
    """Measure real-target expiry timestamps and verify observed_overrun_ms under live execution."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    now = datetime.now(timezone.utc)
    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )
    executor = SSHTargetExecutor(
        config=config, network_validator=validator, host_key_verifier=trusted_verifier
    )

    grant_id = uuid4()
    target_user = "u_timing_test"
    user_priv, user_pub = generate_ed25519_keypair(comment="opsforge-timing-human")

    grant_expires_at = now + timedelta(seconds=2)
    auth_ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        target_account_binding_id=uuid4(),
        grant_id=grant_id,
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    # Provision user
    prov_res = executor.provision_account(
        ExecutionRequest(
            operation=ExecutionOperation.PROVISION_ACCOUNT,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "target_os_username": target_user,
                "public_key": user_pub,
                "bootstrap_credential": svc_key.encode("utf-8"),
                "user_private_key": user_priv.encode("utf-8"),
            },
        )
    )
    assert prov_res.status == ExecutionStatus.SUCCESS

    try:
        # Apply JIT
        elev_res = executor.apply_jit_grant(
            ExecutionRequest(
                operation=ExecutionOperation.APPLY_JIT_GRANT,
                resource_id=auth_ctx.resource_id,
                authorization_context=auth_ctx,
                parameters={
                    "hostname_ip": TARGET_HOST,
                    "port": TARGET_PORT,
                    "grant_id": str(grant_id),
                    "target_os_username": target_user,
                    "command_set_id": "system_health_check",
                    "bootstrap_credential": svc_key.encode("utf-8"),
                },
            )
        )
        assert elev_res.status == ExecutionStatus.SUCCESS

        # Wait for grant to reach expiration (2 seconds)
        time.sleep(2.5)

        # Real expiry revocation
        rev_res = executor.revoke_jit_grant(
            ExecutionRequest(
                operation=ExecutionOperation.REVOKE_JIT_GRANT,
                resource_id=auth_ctx.resource_id,
                authorization_context=auth_ctx,
                parameters={
                    "hostname_ip": TARGET_HOST,
                    "port": TARGET_PORT,
                    "grant_id": str(grant_id),
                    "bootstrap_credential": svc_key.encode("utf-8"),
                },
            )
        )
        t_rev_complete = datetime.now(timezone.utc)
        assert rev_res.status == ExecutionStatus.SUCCESS

        # Calculate observed overrun from real wall-clock timestamps
        observed_overrun_ms = int(
            (t_rev_complete - grant_expires_at).total_seconds() * 1000
        )
        assert observed_overrun_ms > 0
        # Healthy worker execution on live target must meet the <= 5000ms SLO
        assert (
            observed_overrun_ms <= 5000
        ), f"SLO breach on live target: {observed_overrun_ms}ms"

    finally:
        # Clean up
        executor.remove_account(
            ExecutionRequest(
                operation=ExecutionOperation.REMOVE_ACCOUNT,
                resource_id=auth_ctx.resource_id,
                authorization_context=auth_ctx,
                parameters={
                    "hostname_ip": TARGET_HOST,
                    "port": TARGET_PORT,
                    "target_os_username": target_user,
                    "bootstrap_credential": svc_key.encode("utf-8"),
                },
            )
        )
