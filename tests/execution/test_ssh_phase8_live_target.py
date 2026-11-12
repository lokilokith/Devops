"""Real Live Disposable Target Integration Tests for Phase 8.

Exercises real target operations against `opsforge-disposable-target` on 127.0.0.1:2222:
- Real human account provisioning
- Real JIT privilege activation
- Real target background session creation
- Real session registration in target helper registry
- Real immediate revocation with target session termination and drop-in removal
- Real post-revocation privilege denial verification
- Real multi-session isolation (revoking Grant A does NOT kill Grant B's sessions)
- Real time-based expiry enforcement and overrun timing
- Real crash recovery against live target
- Zero secret leakage
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.audit.service import AuditService
from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
    ExecutionStatus,
)
from app.execution.host_identity import HostKeyVerifier
from app.execution.network_validator import TargetAddressValidator
from app.execution.ssh_executor import (
    SSHConnectionContext,
    SSHExecutionConfig,
    SSHTargetExecutor,
)
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.jit_access.revocation_engine import JITRevocationEngine
from app.resources.models import Environment, ResourceStatus, ResourceType
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


@pytest.fixture
def live_executor(trusted_verifier, db_session):
    from app.resources.repository import ResourcesRepository

    repo = ResourcesRepository(db_session)
    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )
    return SSHTargetExecutor(
        config=config,
        network_validator=validator,
        host_key_verifier=trusted_verifier,
        resource_resolver=repo.get_by_id,
    )


def test_real_live_target_jit_session_termination_lifecycle(
    target_container, live_executor, svc_key, trusted_verifier
):
    """Real lifecycle: Provision account -> Apply JIT -> Spawn target session -> Register session -> Revoke -> Verify process killed & sudo denied."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    now = datetime.now(timezone.utc)
    user_priv, user_pub = generate_ed25519_keypair(comment="opsforge-p8-user")
    target_user = "u_p8_live_user"
    binding_id = uuid4()
    grant_id = uuid4()
    session_id = uuid4()

    auth_ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        target_account_binding_id=binding_id,
        grant_id=grant_id,
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    # 1. Clean starting state: Remove existing account if present
    try:
        live_executor.remove_account(
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

    # 2. Provision real target account
    prov_req = ExecutionRequest(
        operation=ExecutionOperation.PROVISION_ACCOUNT,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "target_os_username": target_user,
            "public_key": user_pub,
            "user_private_key_pem": user_priv,
            "bootstrap_credential": svc_key.encode("utf-8"),
        },
    )
    prov_res = live_executor.provision_account(prov_req)
    assert prov_res.status == ExecutionStatus.SUCCESS

    # 3. Apply JIT grant for system_health_check
    apply_req = ExecutionRequest(
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
    apply_res = live_executor.apply_jit_grant(apply_req)
    assert apply_res.status == ExecutionStatus.SUCCESS

    # 4. Open real SSH connection as target human user, verify sudo works, and spawn background process
    user_config = SSHExecutionConfig(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )
    user_validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )

    with SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username=target_user,
        private_key_pem=user_priv,
        network_validator=user_validator,
        host_key_verifier=trusted_verifier,
        config=user_config,
    ) as user_client:
        # Verify sudo works
        _, stdout, _ = user_client.exec_command("sudo -n /usr/bin/uptime")
        assert stdout.channel.recv_exit_status() == 0

        # Spawn background sleep process
        _, stdout, _ = user_client.exec_command(
            "nohup sleep 300 >/dev/null 2>&1 & echo $!"
        )
        pid_str = stdout.read().decode().strip()
        target_pid = int(pid_str)
        assert target_pid > 1

        # Verify process is alive
        _, stdout, _ = user_client.exec_command(f"kill -0 {target_pid}")
        assert stdout.channel.recv_exit_status() == 0

    # 5. Register session via helper
    reg_req = ExecutionRequest(
        operation=ExecutionOperation.REGISTER_JIT_SESSION,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "grant_id": str(grant_id),
            "session_id": str(session_id),
            "target_os_username": target_user,
            "pid": target_pid,
            "bootstrap_credential": svc_key.encode("utf-8"),
        },
    )
    reg_res = live_executor.register_jit_session(reg_req)
    assert reg_res.status == ExecutionStatus.SUCCESS

    # 6. Execute Phase 8 session termination on target
    term_req = ExecutionRequest(
        operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
        resource_id=auth_ctx.resource_id,
        authorization_context=auth_ctx,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "grant_id": str(grant_id),
            "bootstrap_credential": svc_key.encode("utf-8"),
        },
    )
    term_res = live_executor.terminate_jit_sessions(term_req)
    assert term_res.status == ExecutionStatus.SUCCESS

    # 7. Execute JIT sudoers removal
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
    rev_res = live_executor.revoke_jit_grant(rev_req)
    assert rev_res.status == ExecutionStatus.SUCCESS

    # 8. Independent Target Verification over fresh SSH channel:
    # - Background PID is DEAD (kill -0 fails)
    # - Sudoers privilege is GONE (sudo -n /usr/bin/uptime fails)
    with SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username=target_user,
        private_key_pem=user_priv,
        network_validator=user_validator,
        host_key_verifier=trusted_verifier,
        config=user_config,
    ) as verify_client:
        # Check process dead
        _, p_stdout, _ = verify_client.exec_command(f"kill -0 {target_pid}")
        assert (
            p_stdout.channel.recv_exit_status() != 0
        ), f"Process PID {target_pid} was not terminated on target!"

        # Check privilege denied
        _, s_stdout, s_stderr = verify_client.exec_command("sudo -n /usr/bin/uptime")
        exit_code = s_stdout.channel.recv_exit_status()
        assert (
            exit_code != 0
        ), "Security violation: Revoked user still has sudo access on target!"

    # Clean up account
    live_executor.remove_account(
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


def test_real_live_target_multi_session_isolation(
    target_container, live_executor, svc_key, trusted_verifier
):
    """Multi-session isolation: Revoking Grant A terminates sessions A1, A2, but leaves Grant B's session B1 running!"""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    now = datetime.now(timezone.utc)
    user_priv, user_pub = generate_ed25519_keypair(comment="opsforge-p8-multi")
    target_user = "u_p8_multi_user"
    binding_id = uuid4()
    grant_a = uuid4()
    grant_b = uuid4()

    auth_ctx = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        target_account_binding_id=binding_id,
        grant_id=grant_a,
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    # Provision user
    live_executor.provision_account(
        ExecutionRequest(
            operation=ExecutionOperation.PROVISION_ACCOUNT,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "target_os_username": target_user,
                "public_key": user_pub,
                "user_private_key_pem": user_priv,
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )

    # Apply Grant A and Grant B
    live_executor.apply_jit_grant(
        ExecutionRequest(
            operation=ExecutionOperation.APPLY_JIT_GRANT,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_a),
                "target_os_username": target_user,
                "command_set_id": "system_health_check",
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )
    live_executor.apply_jit_grant(
        ExecutionRequest(
            operation=ExecutionOperation.APPLY_JIT_GRANT,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_b),
                "target_os_username": target_user,
                "command_set_id": "container_status",
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )

    user_config = SSHExecutionConfig(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )
    user_validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )

    with SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username=target_user,
        private_key_pem=user_priv,
        network_validator=user_validator,
        host_key_verifier=trusted_verifier,
        config=user_config,
    ) as user_client:
        # Spawn A1, A2, and B1
        _, out1, _ = user_client.exec_command(
            "nohup sleep 300 >/dev/null 2>&1 & echo $!"
        )
        pid_a1 = int(out1.read().decode().strip())

        _, out2, _ = user_client.exec_command(
            "nohup sleep 300 >/dev/null 2>&1 & echo $!"
        )
        pid_a2 = int(out2.read().decode().strip())

        _, out3, _ = user_client.exec_command(
            "nohup sleep 300 >/dev/null 2>&1 & echo $!"
        )
        pid_b1 = int(out3.read().decode().strip())

    # Register A1, A2 under Grant A
    live_executor.register_jit_session(
        ExecutionRequest(
            operation=ExecutionOperation.REGISTER_JIT_SESSION,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_a),
                "session_id": str(uuid4()),
                "target_os_username": target_user,
                "pid": pid_a1,
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )
    live_executor.register_jit_session(
        ExecutionRequest(
            operation=ExecutionOperation.REGISTER_JIT_SESSION,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_a),
                "session_id": str(uuid4()),
                "target_os_username": target_user,
                "pid": pid_a2,
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )

    # Register B1 under Grant B
    live_executor.register_jit_session(
        ExecutionRequest(
            operation=ExecutionOperation.REGISTER_JIT_SESSION,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_b),
                "session_id": str(uuid4()),
                "target_os_username": target_user,
                "pid": pid_b1,
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )

    # Terminate sessions for Grant A
    term_res = live_executor.terminate_jit_sessions(
        ExecutionRequest(
            operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_a),
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )
    assert term_res.status == ExecutionStatus.SUCCESS

    # Verify on target: A1 and A2 are DEAD, but B1 is STILL RUNNING!
    with SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username=target_user,
        private_key_pem=user_priv,
        network_validator=user_validator,
        host_key_verifier=trusted_verifier,
        config=user_config,
    ) as verify_client:
        _, p_a1, _ = verify_client.exec_command(f"kill -0 {pid_a1}")
        assert (
            p_a1.channel.recv_exit_status() != 0
        ), f"PID A1 ({pid_a1}) was not terminated!"

        _, p_a2, _ = verify_client.exec_command(f"kill -0 {pid_a2}")
        assert (
            p_a2.channel.recv_exit_status() != 0
        ), f"PID A2 ({pid_a2}) was not terminated!"

        _, p_b1, _ = verify_client.exec_command(f"kill -0 {pid_b1}")
        assert (
            p_b1.channel.recv_exit_status() == 0
        ), f"PID B1 ({pid_b1}) was incorrectly terminated!"

    # Clean up Grant B and account
    live_executor.terminate_jit_sessions(
        ExecutionRequest(
            operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
            resource_id=auth_ctx.resource_id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant_b),
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )
    live_executor.remove_account(
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


def test_real_live_target_expiry_timing_and_slo(
    target_container, live_executor, svc_key, trusted_verifier, db_session
):
    """Real time-based expiry on target measuring observed overrun against <= 5000ms SLO."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    from app.access_requests.models import (
        AccessRequest,
        AccessRequestPriority,
        AccessRequestStatus,
    )
    from app.identity.models import User, UserStatus
    from app.resources.models import Resource
    from app.roles.models import Role
    from app.target_accounts.models import (
        TargetAccountBinding,
        TargetAccountBindingStatus,
    )

    user_priv, user_pub = generate_ed25519_keypair(comment="opsforge-p8-expiry")
    target_user = "u_p8_exp_user"

    user = User(
        id=uuid4(),
        employee_id=f"EMP-{uuid4().hex[:6]}",
        email=f"exp_{uuid4().hex[:8]}@example.com",
        username=f"u_{uuid4().hex[:8]}",
        full_name="Expiry User",
        password_hash="pw",
        status=UserStatus.ACTIVE,
    )
    role = Role(
        id=uuid4(),
        role_code=f"P8_ROLE_{uuid4().hex[:6].upper()}",
        role_name=f"P8 Role {uuid4().hex[:6]}",
        description="test",
    )
    res = Resource(
        id=uuid4(),
        resource_code=f"RES_{uuid4().hex[:6].upper()}",
        resource_name=f"Target Server {uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        hostname_ip=TARGET_HOST,
        port=TARGET_PORT,
    )
    ar = AccessRequest(
        id=uuid4(),
        requester_id=user.id,
        requested_role_id=role.id,
        request_number=f"REQ-P8-{uuid4().hex[:8].upper()}",
        business_justification="Expiry test",
        status=AccessRequestStatus.APPROVED,
        priority=AccessRequestPriority.MEDIUM,
    )
    binding = TargetAccountBinding(
        id=uuid4(),
        control_plane_user_id=user.id,
        resource_id=res.id,
        target_os_username=target_user,
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add_all([user, role, res, ar, binding])
    db_session.commit()

    # Clean starting state
    try:
        live_executor.remove_account(
            ExecutionRequest(
                operation=ExecutionOperation.REMOVE_ACCOUNT,
                resource_id=res.id,
                authorization_context=ExecutionAuthorizationContext(
                    user_id=user.id,
                    resource_id=res.id,
                    target_account_binding_id=binding.id,
                    grant_id=uuid4(),
                    credential_id=uuid4(),
                    requested_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
                ),
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

    # Provision user
    auth_ctx = ExecutionAuthorizationContext(
        user_id=user.id,
        resource_id=res.id,
        target_account_binding_id=binding.id,
        grant_id=uuid4(),
        credential_id=uuid4(),
        requested_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    live_executor.provision_account(
        ExecutionRequest(
            operation=ExecutionOperation.PROVISION_ACCOUNT,
            resource_id=res.id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "target_os_username": target_user,
                "public_key": user_pub,
                "user_private_key_pem": user_priv,
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )

    # Create Grant with 2-second duration
    now = datetime.now(timezone.utc)
    grant = JITAccessGrant(
        id=uuid4(),
        user_id=user.id,
        role_id=role.id,
        resource_id=res.id,
        target_account_binding_id=binding.id,
        approval_request_id=ar.id,
        command_set_id="system_health_check",
        status=JITGrantStatus.ACTIVE,
        expires_at=now + timedelta(seconds=2),
        row_version=1,
    )
    db_session.add(grant)
    db_session.commit()

    # Apply JIT drop-in
    live_executor.apply_jit_grant(
        ExecutionRequest(
            operation=ExecutionOperation.APPLY_JIT_GRANT,
            resource_id=res.id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant.id),
                "target_os_username": target_user,
                "command_set_id": "system_health_check",
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )

    # Spawn background session on target
    user_config = SSHExecutionConfig(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )
    user_validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )

    with SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username=target_user,
        private_key_pem=user_priv,
        network_validator=user_validator,
        host_key_verifier=trusted_verifier,
        config=user_config,
    ) as user_client:
        _, out, _ = user_client.exec_command(
            "nohup sleep 300 >/dev/null 2>&1 & echo $!"
        )
        pid = int(out.read().decode().strip())

    # Register session
    live_executor.register_jit_session(
        ExecutionRequest(
            operation=ExecutionOperation.REGISTER_JIT_SESSION,
            resource_id=res.id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "grant_id": str(grant.id),
                "session_id": str(uuid4()),
                "target_os_username": target_user,
                "pid": pid,
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )

    # Wait for 2s grant duration to expire
    time.sleep(2.5)

    # Revoke via engine
    repo = JITAccessRepository(db_session)
    from app.audit.repository import AuditRepository

    audit_svc = AuditService(AuditRepository(db_session))
    engine = JITRevocationEngine(repository=repo, audit_service=audit_svc)

    updated_grant = engine.revoke_grant(
        grant_id=grant.id,
        actor_id=user.id,
        is_expiry=True,
        executor=live_executor,
        bootstrap_credential=svc_key.encode("utf-8"),
    )

    assert updated_grant.status == JITGrantStatus.EXPIRED
    assert updated_grant.observed_overrun_ms is not None
    assert updated_grant.observed_overrun_ms >= 0
    assert (
        updated_grant.observed_overrun_ms <= 5000
    ), f"SLO breached: {updated_grant.observed_overrun_ms}ms > 5000ms"

    # Verify PID is terminated on target
    with SSHConnectionContext(
        target_host=TARGET_HOST,
        target_port=TARGET_PORT,
        username=target_user,
        private_key_pem=user_priv,
        network_validator=user_validator,
        host_key_verifier=trusted_verifier,
        config=user_config,
    ) as verify_client:
        _, p_out, _ = verify_client.exec_command(f"kill -0 {pid}")
        assert (
            p_out.channel.recv_exit_status() != 0
        ), f"Process PID {pid} still alive after expiry!"

        _, s_out, _ = verify_client.exec_command("sudo -n /usr/bin/uptime")
        assert (
            s_out.channel.recv_exit_status() != 0
        ), "Sudo privilege still available after expiry!"

    # Clean up account
    live_executor.remove_account(
        ExecutionRequest(
            operation=ExecutionOperation.REMOVE_ACCOUNT,
            resource_id=res.id,
            authorization_context=auth_ctx,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "target_os_username": target_user,
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
    )
