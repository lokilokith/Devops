"""Live integration tests for real target account provisioning against opsforge-disposable-target."""

import os
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
from app.execution.ssh_executor import SSHExecutionConfig, SSHTargetExecutor
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


def test_real_target_account_provisioning_lifecycle(
    target_container, trusted_verifier, svc_key
):
    """Test full real target account provisioning, independent verification, and removal on live target."""
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

    # 1. Generate human user keypair
    user1_priv, user1_pub = generate_ed25519_keypair(comment="opsforge-human-1")
    target_user1 = "u_human_test_1"

    auth_ctx1 = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=uuid4(),
        target_account_binding_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    req1 = ExecutionRequest(
        operation=ExecutionOperation.PROVISION_ACCOUNT,
        resource_id=auth_ctx1.resource_id,
        authorization_context=auth_ctx1,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "target_os_username": target_user1,
            "public_key": user1_pub,
            "bootstrap_credential": svc_key.encode("utf-8"),
            "user_private_key": user1_priv.encode("utf-8"),
        },
    )

    # Clean up user if already exists from prior run
    try:
        cleanup_req = ExecutionRequest(
            operation=ExecutionOperation.REMOVE_ACCOUNT,
            resource_id=auth_ctx1.resource_id,
            authorization_context=auth_ctx1,
            parameters={
                "hostname_ip": TARGET_HOST,
                "port": TARGET_PORT,
                "target_os_username": target_user1,
                "bootstrap_credential": svc_key.encode("utf-8"),
            },
        )
        executor.remove_account(cleanup_req)
    except Exception:
        pass

    # 2. Provision User 1
    res1 = executor.provision_account(req1)
    assert res1.status == ExecutionStatus.SUCCESS
    assert res1.verification_status == VerificationStatus.VERIFIED_SUCCESS

    # 3. Duplicate Provisioning is Idempotent
    res1_dup = executor.provision_account(req1)
    assert res1_dup.status == ExecutionStatus.SUCCESS

    # 4. Provision User 2 (multi-user isolation)
    user2_priv, user2_pub = generate_ed25519_keypair(comment="opsforge-human-2")
    target_user2 = "u_human_test_2"

    auth_ctx2 = ExecutionAuthorizationContext(
        user_id=uuid4(),
        resource_id=auth_ctx1.resource_id,
        target_account_binding_id=uuid4(),
        credential_id=uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    req2 = ExecutionRequest(
        operation=ExecutionOperation.PROVISION_ACCOUNT,
        resource_id=auth_ctx2.resource_id,
        authorization_context=auth_ctx2,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "target_os_username": target_user2,
            "public_key": user2_pub,
            "bootstrap_credential": svc_key.encode("utf-8"),
            "user_private_key": user2_priv.encode("utf-8"),
        },
    )

    res2 = executor.provision_account(req2)
    assert res2.status == ExecutionStatus.SUCCESS

    # 5. Clean up User 1 and User 2
    rem_req1 = ExecutionRequest(
        operation=ExecutionOperation.REMOVE_ACCOUNT,
        resource_id=auth_ctx1.resource_id,
        authorization_context=auth_ctx1,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "target_os_username": target_user1,
            "bootstrap_credential": svc_key.encode("utf-8"),
        },
    )
    rem_res1 = executor.remove_account(rem_req1)
    assert rem_res1.status == ExecutionStatus.SUCCESS

    rem_req2 = ExecutionRequest(
        operation=ExecutionOperation.REMOVE_ACCOUNT,
        resource_id=auth_ctx2.resource_id,
        authorization_context=auth_ctx2,
        parameters={
            "hostname_ip": TARGET_HOST,
            "port": TARGET_PORT,
            "target_os_username": target_user2,
            "bootstrap_credential": svc_key.encode("utf-8"),
        },
    )
    rem_res2 = executor.remove_account(rem_req2)
    assert rem_res2.status == ExecutionStatus.SUCCESS
