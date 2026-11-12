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


def test_real_ssh_rotation_full_vault_and_worker_lifecycle(
    target_container, db_session, trusted_verifier, initial_svc_key, admin_user
):
    """Test full Vault -> RotationWorker -> SSHTargetExecutor -> Target -> Vault CAS commit cycle."""
    if not target_container:
        pytest.skip("Disposable target container is not running")

    from app.resources.models import Resource
    from app.vault.crypto import EncryptionService
    from app.vault.domain import Secret, SecretStatus, SecretVersion
    from app.vault.executor_registry import ExecutorRegistry
    from app.vault.kms_factory import KMSProviderFactory
    from app.vault.models import VaultSecret, VaultSecretVersion
    from app.vault.repository import SqlAlchemyVaultRepository
    from app.vault_lifecycle.models import RotationStatus, SecretRotationPolicy
    from app.vault_lifecycle.service import VaultLifecycleService
    from app.workers.rotation_worker import run_rotation_job

    # 1. Setup Resource
    resource = Resource(
        resource_code="SSH_DISPOSABLE_TARGET_E2E",
        resource_name="Disposable Target E2E",
        connection_method="ssh",
        hostname_ip=TARGET_HOST,
        port=TARGET_PORT,
        status="active",
        created_by=admin_user.id,
    )
    db_session.add(resource)
    db_session.flush()

    # 2. Setup KMS Provider and Encryption Service
    kms_provider = KMSProviderFactory.resolve_active_provider(db_session)
    encryption_service = EncryptionService(kms_provider)

    # 3. Create VaultSecret via SqlAlchemyVaultRepository with initial key
    secret_id = uuid4()
    version_id = uuid4()
    initial_key_bytes = initial_svc_key.encode("utf-8")
    dek, payload, meta = encryption_service.encrypt_payload(
        resource.id, secret_id, initial_key_bytes
    )

    now = datetime.now(timezone.utc)
    init_ver = SecretVersion(
        id=version_id,
        secret_id=secret_id,
        encrypted_dek=dek,
        encrypted_payload=payload,
        metadata=meta,
        created_at=now,
        created_by=admin_user.id,
    )

    domain_secret = Secret(
        id=secret_id,
        resource_id=resource.id,
        status=SecretStatus.ACTIVE,
        row_version=1,
        current_version_id=version_id,
        created_at=now,
        updated_at=now,
        versions=[init_ver],
    )

    vault_repo = SqlAlchemyVaultRepository(db_session)
    vault_repo.save(domain_secret)

    # 4. Attach active Rotation Policy due for rotation
    policy = SecretRotationPolicy(
        vault_secret_id=secret_id,
        status=RotationStatus.ACTIVE,
        rotation_interval_days=30,
        rotation_interval_seconds=30 * 86400,
        next_rotation_at=now - timedelta(minutes=5),
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=30),
        retry_count=0,
    )
    db_session.add(policy)
    db_session.flush()

    # 5. Wire SSHTargetExecutor and Registry
    config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, TARGET_PORT})
    validator = TargetAddressValidator(
        allow_loopback=True, allowed_ports={22, TARGET_PORT}
    )
    executor = SSHTargetExecutor(
        config=config,
        network_validator=validator,
        host_key_verifier=trusted_verifier,
        resource_resolver=lambda rid: (
            resource if rid in (resource.id, secret_id) else None
        ),
    )

    executor_reg = ExecutorRegistry(executors=[executor])

    from app.audit.repository import AuditRepository
    from app.audit.service import AuditService
    from app.vault_lifecycle.repository import SecretRotationPolicyRepository
    from app.workers.rotation_worker import _PrivilegedAuthorizationService

    audit_repo = AuditRepository(db_session)
    audit_svc = AuditService(audit_repo)
    authz_svc = _PrivilegedAuthorizationService()
    policy_repo = SecretRotationPolicyRepository(db_session)
    lifecycle_svc = VaultLifecycleService(
        repository=policy_repo,
        audit_service=audit_svc,
        authz_service=authz_svc,
        session=db_session,
    )

    new_decrypted_key = None

    try:
        # 6. Run Rotation Worker job
        counters = run_rotation_job(
            session=db_session,
            audit_service=audit_svc,
            encryption_service=encryption_service,
            lifecycle_service=lifecycle_svc,
            executor_registry=executor_reg,
        )

        assert counters["attempted"] == 1
        assert counters["succeeded"] == 1

        # 7. Verify Vault DB State after rotation
        secret_model = db_session.get(VaultSecret, secret_id)
        db_session.refresh(secret_model)
        db_session.refresh(policy)

        assert secret_model.status == SecretStatus.ACTIVE
        assert (
            secret_model.row_version == 3
        )  # 1 (init) -> 2 (start_rotation) -> 3 (complete_rotation)
        assert secret_model.current_version_id != version_id

        # 8. Load fresh secret version from Vault and decrypt
        latest_ver = (
            db_session.query(VaultSecretVersion)
            .filter_by(id=secret_model.current_version_id)
            .one()
        )
        assert latest_ver.id != version_id

        from app.vault.domain import SecretMetadata

        recovered_meta = SecretMetadata(
            key_version=latest_ver.key_version,
            algorithm=latest_ver.algorithm,
            nonce=latest_ver.nonce,
            encryption_context=latest_ver.encryption_context,
        )

        new_decrypted_bytes = encryption_service.decrypt_payload(
            secret_model.resource_id,
            secret_model.id,
            latest_ver.encrypted_dek,
            latest_ver.encrypted_payload,
            recovered_meta,
        )
        new_decrypted_key = new_decrypted_bytes.decode("utf-8")
        assert "BEGIN OPENSSH PRIVATE KEY" in new_decrypted_key
        assert new_decrypted_key != initial_svc_key

        # 9. Verify live target authentication with fresh Vault-decrypted key
        with SSHConnectionContext(
            target_host=TARGET_HOST,
            target_port=TARGET_PORT,
            username="opsforge-svc",
            private_key_pem=new_decrypted_key,
            network_validator=validator,
            host_key_verifier=trusted_verifier,
            config=config,
        ) as client:
            _, stdout, _ = client.exec_command("whoami")
            assert stdout.read().decode().strip() == "opsforge-svc"

        # 10. Verify old key is rejected by target
        with pytest.raises(TargetAuthenticationError):
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

    finally:
        # Restore standard initial key in target container
        with open(SVC_KEY_PATH + ".pub", "r", encoding="utf-8") as f:
            std_pub = f.read().strip()
        for key_to_try in [new_decrypted_key, initial_svc_key]:
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
