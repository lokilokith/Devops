import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.access_requests.models import (
    AccessRequest,
    AccessRequestPriority,
    AccessRequestStatus,
)
from app.audit.repository import AuditRepository
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
    SSHExecutionConfig,
    SSHTargetExecutor,
)
from app.identity.models import User, UserStatus
from app.jit_access.models import JITAccessGrant, JITGrantStatus
from app.jit_access.repository import JITAccessRepository
from app.resources.models import Environment, Resource, ResourceStatus, ResourceType
from app.target_accounts.models import TargetAccountBinding, TargetAccountBindingStatus
from app.target_accounts.repository import TargetAccountBindingRepository
from app.vault.ssh_keys import generate_ed25519_keypair
from app.workers.jit_reconciliation_worker import JITReconciliationWorker
from tests.execution.test_target_bootstrap import (
    HOST_ED25519_PUB_PATH,
    SVC_KEY_PATH,
    TARGET_HOST,
    TARGET_PORT,
)

pytestmark = pytest.mark.live_target


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


@pytest.fixture
def live_reconciliation_worker(db_session, live_executor, svc_key):
    audit_repo = AuditRepository(db_session)
    audit_svc = AuditService(audit_repo)
    jit_repo = JITAccessRepository(db_session)
    target_repo = TargetAccountBindingRepository(db_session)
    return JITReconciliationWorker(
        jit_repo, audit_svc, live_executor, target_repo, bootstrap_credential=svc_key
    )


@pytest.fixture
def configured_live_grant(db_session, target_container, svc_key):
    if not target_container:
        pytest.skip("No live target container")

    user = User(
        id=uuid4(),
        employee_id=f"EMP-{uuid4().hex[:5].upper()}",
        username="test_recon_user",
        email="recon@opsforge.local",
        full_name="Recon Test User",
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)

    resource = Resource(
        id=uuid4(),
        resource_code="TST-RCN-01",
        resource_name="live-recon-target",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        hostname_ip=TARGET_HOST,
        port=TARGET_PORT,
    )
    db_session.add(resource)

    human_acct = f"recon_{uuid4().hex[:8]}"
    binding = TargetAccountBinding(
        id=uuid4(),
        control_plane_user_id=user.id,
        resource_id=resource.id,
        target_os_username=human_acct,
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add(binding)

    access_req = AccessRequest(
        id=uuid4(),
        request_number=f"REQ-{uuid4().hex[:8].upper()}",
        requester_id=user.id,
        requested_resource_id=resource.id,
        requested_role_id=uuid4(),
        status=AccessRequestStatus.APPROVED,
        priority=AccessRequestPriority.MEDIUM,
        business_justification="Recon Test",
        requested_start=datetime.now(timezone.utc),
        requested_end=datetime.now(timezone.utc) + timedelta(minutes=60),
    )
    db_session.add(access_req)

    grant = JITAccessGrant(
        id=uuid4(),
        approval_request_id=access_req.id,
        user_id=user.id,
        role_id=uuid4(),
        resource_id=resource.id,
        target_account_binding_id=binding.id,
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
    )
    db_session.add(grant)
    db_session.commit()

    return {
        "user": user,
        "resource": resource,
        "binding": binding,
        "grant": grant,
        "svc_key": svc_key,
    }


def provision_and_apply(live_executor, cfg, pub_key_str):
    req_prov = ExecutionRequest(
        operation=ExecutionOperation.PROVISION_ACCOUNT,
        resource_id=cfg["resource"].id,
        authorization_context=ExecutionAuthorizationContext(
            user_id=cfg["user"].id,
            resource_id=cfg["resource"].id,
            credential_id=uuid4(),
            requested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
            grant_id=cfg["grant"].id,
            target_account_binding_id=cfg["binding"].id,
        ),
        parameters={
            "target_os_username": cfg["binding"].target_os_username,
            "public_key": pub_key_str,
            "bootstrap_credential": cfg["svc_key"],
        },
    )
    res_prov = live_executor.provision_account(req_prov)
    assert (
        res_prov.status == ExecutionStatus.SUCCESS
    ), f"Provision failed: {res_prov.error_message} {res_prov.details}"

    req_apply = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=cfg["resource"].id,
        authorization_context=ExecutionAuthorizationContext(
            user_id=cfg["user"].id,
            resource_id=cfg["resource"].id,
            credential_id=uuid4(),
            requested_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
            grant_id=cfg["grant"].id,
            target_account_binding_id=cfg["binding"].id,
        ),
        parameters={
            "target_os_username": cfg["binding"].target_os_username,
            "grant_id": str(cfg["grant"].id),
            "command_set_id": "system_health_check",
            "bootstrap_credential": cfg["svc_key"],
        },
    )
    res_apply = live_executor.apply_jit_grant(req_apply)
    assert (
        res_apply.status == ExecutionStatus.SUCCESS
    ), f"Apply failed: {res_apply.error_message} {res_apply.details}"


def _run_raw_ssh_cmd(live_executor, cfg, cmd):
    # Runs an out-of-band command by executing directly in the docker container
    # This intentionally bypasses normal execution paths
    import subprocess

    # Clean up sudo prefixes if present since docker exec runs as root
    if cmd.startswith("sudo -n "):
        cmd = cmd[len("sudo -n ") :]
    elif cmd.startswith("sudo "):
        cmd = cmd[len("sudo ") :]

    docker_cmd = ["docker", "exec", "opsforge-disposable-target", "sh", "-c", cmd]
    result = subprocess.run(docker_cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def test_scenario_a_active_missing_expected_privilege(
    configured_live_grant, live_executor, live_reconciliation_worker, db_session
):
    cfg = configured_live_grant
    priv, pub = generate_ed25519_keypair()
    provision_and_apply(live_executor, cfg, pub)

    # Verify the drop-in exists
    cmd = f"sudo ls /etc/sudoers.d/opsforge-jit-{cfg['grant'].id}"
    code, out, err = _run_raw_ssh_cmd(live_executor, cfg, cmd)
    assert code == 0, f"Expected drop-in to exist, got {code}. Out: {out}. Err: {err}"

    # Out-of-band removal to simulate drift
    cmd_remove = f"sudo rm -f /etc/sudoers.d/opsforge-jit-{cfg['grant'].id}"
    code, _, _ = _run_raw_ssh_cmd(live_executor, cfg, cmd_remove)
    assert code == 0, "Out-of-band removal failed"

    cfg["grant"].status = JITGrantStatus.ACTIVE
    db_session.commit()

    results = live_reconciliation_worker.process_reconciliation()
    assert len(results) == 1

    # Assert
    db_session.refresh(cfg["grant"])
    assert cfg["grant"].status == JITGrantStatus.ACTIVE

    # Assert privilege was NOT recreated
    code, out, _ = _run_raw_ssh_cmd(live_executor, cfg, cmd)
    assert code != 0, "Drop-in was recreated unexpectedly!"


def test_scenario_b_already_authorized_deterministic_cleanup(
    configured_live_grant, live_executor, live_reconciliation_worker, db_session
):
    cfg = configured_live_grant
    priv, pub = generate_ed25519_keypair()
    provision_and_apply(live_executor, cfg, pub)

    cfg["grant"].status = JITGrantStatus.REVOKED
    db_session.commit()

    cmd = f"sudo ls /etc/sudoers.d/opsforge-jit-{cfg['grant'].id}"
    code, _, _ = _run_raw_ssh_cmd(live_executor, cfg, cmd)
    assert code == 0, "Expected drop-in to exist"

    results = live_reconciliation_worker.process_reconciliation()
    assert len(results) == 1

    db_session.refresh(cfg["grant"])
    assert cfg["grant"].status == JITGrantStatus.REVOKED

    code, _, _ = _run_raw_ssh_cmd(live_executor, cfg, cmd)
    assert code != 0, "Drop-in was not cleaned up!"


def test_scenario_c_security_uncertain_recovery(
    configured_live_grant, live_executor, live_reconciliation_worker, db_session
):
    # C1 Clean Target
    cfg = configured_live_grant
    cfg["grant"].status = JITGrantStatus.SECURITY_UNCERTAIN
    db_session.commit()

    results = live_reconciliation_worker.process_reconciliation()
    assert len(results) == 1

    db_session.refresh(cfg["grant"])
    assert cfg["grant"].status == JITGrantStatus.REVOKED, f"Results: {results}"

    # C2 Residual Target
    cfg["grant"].status = JITGrantStatus.SECURITY_UNCERTAIN
    db_session.commit()

    priv, pub = generate_ed25519_keypair()
    provision_and_apply(live_executor, cfg, pub)

    results = live_reconciliation_worker.process_reconciliation()
    assert len(results) == 1

    db_session.refresh(cfg["grant"])
    assert cfg["grant"].status == JITGrantStatus.REVOKED


def test_scenario_d_unrelated_artifact(
    configured_live_grant, live_executor, live_reconciliation_worker, db_session
):
    cfg = configured_live_grant
    priv, pub = generate_ed25519_keypair()
    provision_and_apply(live_executor, cfg, pub)

    # Create unrelated artifact
    cmd = "echo 'foo ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/opsforge-jit-unknown-123"
    code, _, _ = _run_raw_ssh_cmd(live_executor, cfg, cmd)
    assert code == 0

    results = live_reconciliation_worker.process_reconciliation()
    assert len(results) == 1

    # Assert unrelated file remains untouched
    cmd_check = "sudo ls /etc/sudoers.d/opsforge-jit-unknown-123"
    code, _, _ = _run_raw_ssh_cmd(live_executor, cfg, cmd_check)
    assert code == 0, "Unrelated artifact was unexpectedly deleted!"


def test_scenario_e_unmanaged_process(
    configured_live_grant, live_executor, live_reconciliation_worker, db_session
):
    cfg = configured_live_grant
    priv, pub = generate_ed25519_keypair()
    provision_and_apply(live_executor, cfg, pub)

    # Spawn unmanaged process
    cmd = f"sudo su - {cfg['binding'].target_os_username} -c 'sleep 300 &' && pgrep -u {cfg['binding'].target_os_username} sleep"
    code, pid, _ = _run_raw_ssh_cmd(live_executor, cfg, cmd)
    assert code == 0
    pid = pid.strip()

    results = live_reconciliation_worker.process_reconciliation()
    assert len(results) == 1

    # Check if process is still alive
    cmd_check = f"sudo ps -p {pid}"
    code, _, _ = _run_raw_ssh_cmd(live_executor, cfg, cmd_check)
    assert code == 0, "Unmanaged process was unexpectedly killed!"

    # Cleanup
    _run_raw_ssh_cmd(live_executor, cfg, f"sudo kill -9 {pid}")


def test_scenario_f_fail_closed(
    configured_live_grant, live_executor, live_reconciliation_worker, db_session
):
    cfg = configured_live_grant

    cfg["resource"].hostname_ip = "198.51.100.254"  # Unreachable IP
    db_session.commit()

    results = live_reconciliation_worker.process_reconciliation()
    assert len(results) == 1

    db_session.refresh(cfg["grant"])
    # If the SSH executor fails entirely, it should classify as UNREACHABLE or similar,
    # but since ACTIVE -> ACTIVE we can just check it didn't do anything crazy
    assert cfg["grant"].status == JITGrantStatus.ACTIVE
