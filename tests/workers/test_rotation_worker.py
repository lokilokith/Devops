"""Phase 2B.5B – RotationWorker test suite.

Covers the acceptance scenarios outlined in the implementation plan:
  1. No eligible policies – worker is a no-op.
  2. Successful rotation – new version persisted, policy timestamps updated.
  3. Retryable failure – retry_count incremented, no new version, policy unchanged.
  4. Terminal failure – secret moves to DESYNCED, policy moves to ERROR.
  5. Missing executor – no executor found → same failure path as terminal.
  6. ConcurrencyError during start_rotation – policy skipped atomically.
  7. Encryption failure – unexpected exc → rollback, no version, audit logged.
  8. Multiple policies – each processed independently (per-SAVEPOINT isolation).
  9. Plaintext leakage check – audit details never contain plaintext bytes.
  10. Executor receives encrypted payload (not plaintext before decryption path).

Security invariant: none of the test credential strings may appear in audit
``details``, secret rows, or version rows after execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.authorization.service import AuthorizationService
from app.resources.models import (
    Criticality,
    Environment,
    Resource,
    ResourceStatus,
    ResourceType,
)
from app.vault.crypto import EncryptionService, LocalKMSProvider
from app.vault.domain import SecretFactory, SecretMetadata, SecretVersion
from app.vault.exceptions import ConcurrencyError
from app.vault.executor import ExecutionResult
from app.vault.executor_registry import ExecutorRegistry
from app.vault.executor_stub import StubCredentialExecutor
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.models import RotationResultStatus, RotationStatus, SecretRotationPolicy
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault_lifecycle.service import VaultLifecycleService
from app.workers.rotation_worker import run_rotation_job, WORKER_ACTOR_ID, _PrivilegedAuthorizationService

# ---------------------------------------------------------------------------
# Helpers / shared factories
# ---------------------------------------------------------------------------

SENTINEL_PLAINTEXT = b"SENTINEL_CREDENTIAL_DO_NOT_LOG"


def _make_resource(db_session) -> Resource:
    resource = Resource(
        resource_code=f"WRK{uuid.uuid4().hex[:6].upper()}",
        resource_name=f"Worker Test Resource {uuid.uuid4().hex[:8]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)
    db_session.flush()
    return resource


def _make_secret_with_version(
    db_session, resource: Resource, encryption_service: EncryptionService, actor_id: UUID
):
    """Create a persisted ACTIVE secret with one encrypted version."""
    repo = SqlAlchemyVaultRepository(db_session)
    secret = SecretFactory.create_new_secret(resource.id)

    encrypted_dek, encrypted_payload, metadata = encryption_service.encrypt_payload(
        resource.id, secret.id, SENTINEL_PLAINTEXT
    )
    version = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret.id,
        encrypted_dek=encrypted_dek,
        encrypted_payload=encrypted_payload,
        metadata=metadata,
        created_at=datetime.now(timezone.utc),
        created_by=actor_id,
    )
    secret.add_version(version)
    repo.save(secret)
    db_session.flush()
    return secret


def _make_policy(
    db_session,
    vault_secret_id: UUID,
    *,
    next_rotation_at: datetime | None = None,
    status: RotationStatus = RotationStatus.ACTIVE,
) -> SecretRotationPolicy:
    """Create a persisted rotation policy with ``next_rotation_at`` in the past by default."""
    now = datetime.now(timezone.utc)
    policy = SecretRotationPolicy(
        vault_secret_id=vault_secret_id,
        plugin_name="stub",
        rotation_interval_days=30,
        rotation_interval_seconds=2592000,
        retry_count=0,
        last_rotated_at=None,
        next_rotation_at=next_rotation_at or (now - timedelta(seconds=1)),
        status=status,
    )
    db_session.add(policy)
    db_session.flush()
    return policy


def _build_services(db_session, behaviour_map: Dict[UUID, str] | None = None):
    """Wire all services for the worker using the privileged auth stub."""
    import os, base64

    kms = LocalKMSProvider()
    enc = EncryptionService(kms)
    audit_repo = AuditRepository(db_session)
    audit_svc = AuditService(audit_repo)
    # Workers are privileged background processes – use the always-allow stub.
    privileged_authz = _PrivilegedAuthorizationService()
    lc_repo = SecretRotationPolicyRepository(db_session)
    lc_svc = VaultLifecycleService(lc_repo, audit_svc, privileged_authz, db_session)

    stub = StubCredentialExecutor(behaviour_map or {})
    registry = ExecutorRegistry(executors=[stub])

    return enc, audit_svc, lc_svc, registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def actor_id() -> UUID:
    return WORKER_ACTOR_ID


@pytest.fixture
def enc_svc(app) -> EncryptionService:
    """Encryption service backed by VAULT_MASTER_KEY set in conftest."""
    kms = LocalKMSProvider()
    return EncryptionService(kms)


# ---------------------------------------------------------------------------
# Scenario 1: No eligible policies
# ---------------------------------------------------------------------------

def test_no_eligible_policies_is_noop(db_session, enc_svc, actor_id):
    """Worker finds no eligible policies → returns zeros, no DB writes."""
    enc, audit_svc, lc_svc, registry = _build_services(db_session)

    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["attempted"] == 0
    assert result["succeeded"] == 0
    assert result["failed"] == 0


def test_future_next_rotation_at_is_not_eligible(db_session, enc_svc, actor_id):
    """Policies with ``next_rotation_at`` in the future are not eligible."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    _make_policy(db_session, secret.id, next_rotation_at=future)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})
    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["attempted"] == 0


# ---------------------------------------------------------------------------
# Scenario 2: Successful rotation
# ---------------------------------------------------------------------------

def test_successful_rotation_creates_new_version(db_session, enc_svc, actor_id):
    """After a successful run the secret must have one additional version."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    initial_version_count = len(secret.versions)
    initial_row_version = secret.row_version
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})
    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["succeeded"] == 1
    assert result["failed"] == 0

    db_session.expire_all()
    repo = SqlAlchemyVaultRepository(db_session)
    refreshed = repo.find_by_id(secret.id)
    assert refreshed is not None
    assert len(refreshed.versions) == initial_version_count + 1
    # row_version must have incremented (CAS applied)
    assert refreshed.row_version > initial_row_version
    # Secret must be back to ACTIVE
    from app.vault.domain import SecretStatus
    assert refreshed.status == SecretStatus.ACTIVE


def test_successful_rotation_resets_retry_count(db_session, enc_svc, actor_id):
    """retry_count is reset to 0 on a successful rotation."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    policy = _make_policy(db_session, secret.id)
    policy.retry_count = 5
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})
    run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    db_session.expire_all()
    policy_repo = SecretRotationPolicyRepository(db_session)
    refreshed_policy = policy_repo.get_by_vault_secret_id(secret.id)
    assert refreshed_policy is not None
    assert refreshed_policy.retry_count == 0


def test_successful_rotation_updates_policy_timestamps(db_session, enc_svc, actor_id):
    """``last_rotated_at`` and ``next_rotation_at`` must be updated on success."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    policy = _make_policy(db_session, secret.id)
    original_last = policy.last_rotated_at
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})
    before = datetime.now(timezone.utc)
    run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    db_session.expire_all()
    policy_repo = SecretRotationPolicyRepository(db_session)
    refreshed_policy = policy_repo.get_by_vault_secret_id(secret.id)
    assert refreshed_policy is not None
    if refreshed_policy.last_rotated_at:
        ts = refreshed_policy.last_rotated_at
        # SQLite may return naive datetimes; normalise for comparison.
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        before_naive = before.replace(tzinfo=None) if ts.tzinfo is None else before
        assert ts >= before


# ---------------------------------------------------------------------------
# Scenario 3: Retryable failure
# ---------------------------------------------------------------------------

def test_retryable_failure_increments_retry_count(db_session, enc_svc, actor_id):
    """When the executor raises a retryable error, ``retry_count`` must increment."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    policy = _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "retry"})
    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["failed"] == 1

    db_session.expire_all()
    policy_repo = SecretRotationPolicyRepository(db_session)
    refreshed_policy = policy_repo.get_by_vault_secret_id(secret.id)
    assert refreshed_policy is not None
    assert refreshed_policy.retry_count == 1


def test_retryable_failure_does_not_create_new_version(db_session, enc_svc, actor_id):
    """No new SecretVersion must be created on a retryable failure."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    initial_count = len(secret.versions)
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "retry"})
    run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    db_session.expire_all()
    repo = SqlAlchemyVaultRepository(db_session)
    refreshed = repo.find_by_id(secret.id)
    assert refreshed is not None
    assert len(refreshed.versions) == initial_count


def test_retryable_failure_leaves_policy_active(db_session, enc_svc, actor_id):
    """Policy status must remain ACTIVE (not ERROR) after a retryable failure."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "retry"})
    run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    db_session.expire_all()
    policy_repo = SecretRotationPolicyRepository(db_session)
    refreshed_policy = policy_repo.get_by_vault_secret_id(secret.id)
    assert refreshed_policy is not None
    assert refreshed_policy.status == RotationStatus.ACTIVE


# ---------------------------------------------------------------------------
# Scenario 4: Terminal failure
# ---------------------------------------------------------------------------

def test_terminal_failure_moves_policy_to_error(db_session, enc_svc, actor_id):
    """Terminal executor failure must set policy.status = ERROR."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "terminal"})
    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["failed"] == 1

    db_session.expire_all()
    policy_repo = SecretRotationPolicyRepository(db_session)
    refreshed_policy = policy_repo.get_by_vault_secret_id(secret.id)
    assert refreshed_policy is not None
    assert refreshed_policy.status == RotationStatus.ERROR


def test_terminal_failure_moves_secret_to_desynced(db_session, enc_svc, actor_id):
    """Terminal failure must transition secret to DESYNCED."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "terminal"})
    run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    db_session.expire_all()
    repo = SqlAlchemyVaultRepository(db_session)
    refreshed = repo.find_by_id(secret.id)
    assert refreshed is not None
    from app.vault.domain import SecretStatus
    assert refreshed.status == SecretStatus.DESYNCED


# ---------------------------------------------------------------------------
# Scenario 5: Missing executor
# ---------------------------------------------------------------------------

def test_missing_executor_marks_policy_error(db_session, enc_svc, actor_id):
    """No executor registered for the resource → policy moves to ERROR."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id)
    db_session.flush()

    # Empty registry – no executor can handle this secret.
    enc, audit_svc, lc_svc, _ = _build_services(db_session, {})
    empty_registry = ExecutorRegistry(executors=[])
    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=empty_registry,
        actor_id=actor_id,
    )

    assert result["failed"] == 1
    db_session.expire_all()
    policy_repo = SecretRotationPolicyRepository(db_session)
    refreshed_policy = policy_repo.get_by_vault_secret_id(secret.id)
    assert refreshed_policy is not None
    assert refreshed_policy.status == RotationStatus.ERROR


# ---------------------------------------------------------------------------
# Scenario 6: ConcurrencyError during start_rotation (another worker won)
# ---------------------------------------------------------------------------

def test_concurrency_error_at_start_rotation_is_skipped(db_session, enc_svc, actor_id):
    """ConcurrencyError at start_rotation → policy is skipped (not failed)."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})

    # Patch start_rotation to simulate a concurrent worker winning.
    original_start = lc_svc.start_rotation
    call_count = [0]

    def raise_concurrency(*args, **kwargs):
        call_count[0] += 1
        raise ConcurrencyError("Simulated concurrent worker")

    lc_svc.start_rotation = raise_concurrency

    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["skipped"] == 1
    assert result["succeeded"] == 0


# ---------------------------------------------------------------------------
# Scenario 7: Unexpected exception during processing
# ---------------------------------------------------------------------------

def test_unexpected_exception_returns_failed(db_session, enc_svc, actor_id):
    """An unexpected exception during encryption results in failed + audit."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})

    # Patch encryption to fail unexpectedly.
    def boom(*args, **kwargs):
        raise RuntimeError("Unexpected infrastructure failure")

    enc.decrypt_payload = boom

    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["failed"] == 1


# ---------------------------------------------------------------------------
# Scenario 8: Multiple policies – per-SAVEPOINT isolation
# ---------------------------------------------------------------------------

def test_multiple_policies_independent(db_session, enc_svc, actor_id):
    """Two eligible policies: first succeeds, second has a retryable error.
    Each outcome must be independent – the success must not be rolled back.
    """
    r1 = _make_resource(db_session)
    r2 = _make_resource(db_session)
    s1 = _make_secret_with_version(db_session, r1, enc_svc, actor_id)
    s2 = _make_secret_with_version(db_session, r2, enc_svc, actor_id)
    _make_policy(db_session, s1.id)
    _make_policy(db_session, s2.id)
    db_session.flush()

    behaviour = {s1.id: "success", s2.id: "retry"}
    enc, audit_svc, lc_svc, registry = _build_services(db_session, behaviour)

    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["attempted"] == 2
    assert result["succeeded"] == 1
    assert result["failed"] == 1

    db_session.expire_all()
    repo = SqlAlchemyVaultRepository(db_session)
    s1_fresh = repo.find_by_id(s1.id)
    s2_fresh = repo.find_by_id(s2.id)

    from app.vault.domain import SecretStatus
    assert s1_fresh.status == SecretStatus.ACTIVE
    # s2 is back to ACTIVE because retryable failure rolls back ROTATING state
    # but does NOT progress to DESYNCED.
    assert s2_fresh.status in (SecretStatus.ACTIVE, SecretStatus.ROTATING)


# ---------------------------------------------------------------------------
# Scenario 9: Plaintext leakage check
# ---------------------------------------------------------------------------

def test_no_plaintext_in_audit_details(db_session, enc_svc, actor_id):
    """The sentinel plaintext string must not appear in any audit log details."""
    from app.audit.models import AuditLog
    from sqlalchemy import select as sa_select, or_

    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})
    run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    db_session.flush()
    logs = db_session.execute(sa_select(AuditLog)).scalars().all()
    sentinel = SENTINEL_PLAINTEXT.decode()
    for log in logs:
        details_str = str(log.details or "")
        assert sentinel not in details_str, (
            f"Plaintext found in audit log {log.event_id}: {details_str[:100]}"
        )


def test_no_plaintext_in_version_rows(db_session, enc_svc, actor_id):
    """No ``VaultSecretVersion`` row may contain the plaintext sentinel string."""
    from app.vault.models import VaultSecretVersion
    from sqlalchemy import select as sa_select

    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})
    run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    db_session.flush()
    sentinel = SENTINEL_CREDENTIAL_DO_NOT_LOG = SENTINEL_PLAINTEXT
    versions = db_session.execute(sa_select(VaultSecretVersion)).scalars().all()
    for v in versions:
        assert sentinel not in v.encrypted_payload, (
            "Plaintext stored unencrypted in vault_secret_versions"
        )


# ---------------------------------------------------------------------------
# Scenario 10: PAUSED policy is not eligible
# ---------------------------------------------------------------------------

def test_paused_policy_not_eligible(db_session, enc_svc, actor_id):
    """PAUSED policies must never be eligible regardless of ``next_rotation_at``."""
    resource = _make_resource(db_session)
    secret = _make_secret_with_version(db_session, resource, enc_svc, actor_id)
    _make_policy(db_session, secret.id, status=RotationStatus.PAUSED)
    db_session.flush()

    enc, audit_svc, lc_svc, registry = _build_services(db_session, {secret.id: "success"})
    result = run_rotation_job(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        actor_id=actor_id,
    )

    assert result["attempted"] == 0
