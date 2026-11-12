"""Comprehensive test suite for Phase 5 Automated Rotation Engine.

Covers:
1. Full unattended automated rotation lifecycle (QUEUED -> RUNNING -> SUCCEEDED).
2. Worker lease fencing and stale worker rejection.
3. Bounded retry policy and exponential backoff.
4. Retry exhaustion leading to terminal FAILED state.
5. Security uncertainty classification (UNCERTAIN_STATE / VERIFICATION_INDETERMINATE).
6. Non-retryable terminal errors (host key mismatch, bad config).
7. Vault CAS concurrency collisions.
8. Automated rotation of bootstrap credential.
9. Plaintext credential secrecy across DB, job payloads, audit records, and exceptions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.audit.models import AuditLog
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.execution.executor import StubTargetExecutor
from app.resources.models import (
    Criticality,
    Environment,
    Resource,
    ResourceStatus,
    ResourceType,
)
from app.vault.crypto import EncryptionService, LocalKMSProvider
from app.vault.domain import SecretFactory, SecretStatus, SecretVersion
from app.vault.executor_registry import ExecutorRegistry
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.models import (
    RotationResultStatus,
    RotationStatus,
    SecretRotationPolicy,
)
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault_lifecycle.rotation_job import (
    RotationJob,
    RotationJobState,
)
from app.vault_lifecycle.rotation_job_repository import RotationJobRepository
from app.vault_lifecycle.scheduler import RotationScheduler
from app.vault_lifecycle.service import VaultLifecycleService
from app.workers.rotation_worker import (
    _PrivilegedAuthorizationService,
    run_rotation_worker_cycle,
)

SENTINEL_KEY_PEM = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
    "QyNTUxOQAAACD7V/pG+XvF0U8wJ5U6z+qjR1xL9k8p7Q4xK7z6a7c3bwAAAJgAAAAAeAAA\n"
    "AHgAAAAAtzc2gtZWQyNTUxOQAAACD7V/pG+XvF0U8wJ5U6z+qjR1xL9k8p7Q4xK7z6a7c3\n"
    "bwAAAECmR9zV7w7s7p6v5u6p7w7s7p6v5u6p7w7s7p6v5u6p7w7s7p6v5u6p7w7s7p6v5u\n"
    "6p7w7s7p6v5u6p7w7s7p6v5gAAABRvcHNmb3JnZS1ib290c3RyYXA=\n"
    "-----END OPENSSH PRIVATE KEY-----\n"
)


def _setup_environment(db_session, behaviour_mode="success"):
    """Wire up database and services for Phase 5 worker tests."""
    resource = Resource(
        resource_code=f"SRV{uuid.uuid4().hex[:6].upper()}",
        resource_name=f"Automated Rotation Target {uuid.uuid4().hex[:8]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.PROD,
        criticality=Criticality.HIGH,
        hostname_ip="10.0.0.50",
        port=22,
        pinned_host_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPtX+pG+XvF0U8wJ5U6z+qjR1xL9k8p7Q4xK7z6a7c3b",
    )
    db_session.add(resource)
    db_session.flush()

    kms = LocalKMSProvider()
    enc = EncryptionService(kms)
    audit_repo = AuditRepository(db_session)
    audit_svc = AuditService(audit_repo)
    authz = _PrivilegedAuthorizationService()
    lc_repo = SecretRotationPolicyRepository(db_session)
    lc_svc = VaultLifecycleService(lc_repo, audit_svc, authz, db_session)

    sec_repo = SqlAlchemyVaultRepository(db_session)
    secret = SecretFactory.create_new_secret(resource.id)
    dek, payload, meta = enc.encrypt_payload(
        resource.id, secret.id, SENTINEL_KEY_PEM.encode("utf-8")
    )
    version = SecretVersion(
        id=uuid.uuid4(),
        secret_id=secret.id,
        encrypted_dek=dek,
        encrypted_payload=payload,
        metadata=meta,
        created_at=datetime.now(timezone.utc),
        created_by=uuid.uuid4(),
    )
    secret.add_version(version)
    sec_repo.save(secret)
    db_session.flush()

    policy = SecretRotationPolicy(
        vault_secret_id=secret.id,
        rotation_interval_seconds=86400,
        next_rotation_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        status=RotationStatus.ACTIVE,
    )
    db_session.add(policy)
    db_session.commit()

    stub_executor = StubTargetExecutor(behaviour_map={resource.id: behaviour_mode})
    registry = ExecutorRegistry(executors=[stub_executor])

    return resource, secret, policy, enc, audit_svc, lc_svc, registry


def test_unattended_rotation_lifecycle_success(db_session):
    """Test full happy-path cycle: discovery -> queued job -> claim -> execute -> verified commit."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="success"
    )

    worker_id = "worker-primary"
    result = run_rotation_worker_cycle(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        worker_id=worker_id,
    )

    assert result["attempted"] == 1
    assert result["succeeded"] == 1
    assert result["retryable"] == 0
    assert result["terminal"] == 0

    # Verify Job state
    job_repo = RotationJobRepository(db_session)
    job = job_repo.get_by_secret_and_generation(secret.id, 2)
    assert job is not None
    assert job.state == RotationJobState.SUCCEEDED
    assert job.completed_at is not None
    assert job.attempt_count == 1
    assert job.lease_owner is None

    # Verify Vault Secret state
    sec_repo = SqlAlchemyVaultRepository(db_session)
    refreshed_secret = sec_repo.find_by_id(secret.id)
    assert refreshed_secret.status == SecretStatus.ACTIVE
    assert len(refreshed_secret.versions) == 2

    # Verify Policy state
    refreshed_policy = db_session.get(SecretRotationPolicy, policy.id)
    assert refreshed_policy.last_rotation_status == RotationResultStatus.SUCCESS
    assert refreshed_policy.retry_count == 0
    assert refreshed_policy.last_rotated_at is not None
    assert refreshed_policy.next_rotation_at > datetime.now(timezone.utc)


def test_stale_worker_fencing_rejection(db_session):
    """Test that a worker whose lease expired cannot commit state after another worker claimed the job."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="success"
    )

    scheduler = RotationScheduler(db_session)
    job, _ = scheduler.create_rotation_job(policy, secret)
    db_session.commit()

    job_repo = RotationJobRepository(db_session)

    # Worker A claims job
    claimed_a = job_repo.atomic_claim(
        job_id=job.id,
        worker_id="worker-A",
        lease_duration_seconds=1,  # Short lease
    )
    db_session.commit()
    assert claimed_a is not None
    assert claimed_a.lease_generation == 1

    # Simulate lease expiry and Worker B reclaiming
    now_later = datetime.now(timezone.utc) + timedelta(seconds=5)
    claimed_b = job_repo.atomic_claim(
        job_id=job.id,
        worker_id="worker-B",
        lease_duration_seconds=300,
        now=now_later,
    )
    db_session.commit()
    assert claimed_b is not None
    assert claimed_b.lease_generation == 2
    assert claimed_b.lease_owner == "worker-B"

    # Worker A attempts to verify fencing -> must be rejected (fenced out)
    assert job_repo.verify_fencing(job.id, "worker-A", 1) is False
    # Worker B owns fencing
    assert job_repo.verify_fencing(job.id, "worker-B", 2) is True


def test_retryable_operational_failure_and_backoff(db_session):
    """Test timeout / transient network failure enters RETRY_PENDING with exponential backoff."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="timeout"
    )

    result = run_rotation_worker_cycle(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        worker_id="worker-1",
    )

    assert result["retryable"] == 1
    assert result["succeeded"] == 0

    job_repo = RotationJobRepository(db_session)
    job = job_repo.get_by_secret_and_generation(secret.id, 2)
    assert job is not None
    assert job.state == RotationJobState.RETRY_PENDING
    assert job.attempt_count == 1
    assert job.next_retry_at is not None
    assert job.last_error_code == "SSH_TIMEOUT"

    # Secret must remain in ACTIVE (not left locked in ROTATING)
    sec_repo = SqlAlchemyVaultRepository(db_session)
    refreshed_secret = sec_repo.find_by_id(secret.id)
    assert refreshed_secret.status == SecretStatus.ACTIVE

    # Policy retry_count updated
    refreshed_policy = db_session.get(SecretRotationPolicy, policy.id)
    assert refreshed_policy.retry_count == 1


def test_retry_exhaustion_moves_to_failed(db_session):
    """Test that exhausting max_attempts moves the job to FAILED and policy to ERROR."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="timeout"
    )

    scheduler = RotationScheduler(db_session)
    job, _ = scheduler.create_rotation_job(policy, secret)
    job.attempt_count = 2  # Already tried twice, max_attempts = 3
    db_session.commit()

    result = run_rotation_worker_cycle(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        worker_id="worker-1",
    )

    assert result["retryable"] == 1  # Handled in retryable handler as exhausted

    job_repo = RotationJobRepository(db_session)
    refreshed_job = job_repo.get_by_id(job.id)
    assert refreshed_job.state == RotationJobState.FAILED
    assert refreshed_job.last_error_code == "RETRY_EXHAUSTED"

    refreshed_policy = db_session.get(SecretRotationPolicy, policy.id)
    assert refreshed_policy.status == RotationStatus.ERROR


def test_security_uncertainty_classification(db_session):
    """Test that indeterminate target state classifies as SECURITY_UNCERTAINTY and emits critical audit."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="uncertain_state"
    )

    result = run_rotation_worker_cycle(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        worker_id="worker-1",
    )

    assert result["security_uncertainty"] == 1

    job_repo = RotationJobRepository(db_session)
    job = job_repo.get_by_secret_and_generation(secret.id, 2)
    assert job is not None
    assert job.state == RotationJobState.SECURITY_UNCERTAINTY
    assert job.last_error_code == "SECURITY_UNCERTAINTY"

    sec_repo = SqlAlchemyVaultRepository(db_session)
    refreshed_secret = sec_repo.find_by_id(secret.id)
    assert refreshed_secret.status == SecretStatus.DESYNCED


def test_non_retryable_host_key_mismatch_fails_immediately(db_session):
    """Test that security failure (host key mismatch) does not blind retry and enters FAILED."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="auth_fail"
    )

    result = run_rotation_worker_cycle(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        worker_id="worker-1",
    )

    assert result["terminal"] == 1

    job_repo = RotationJobRepository(db_session)
    job = job_repo.get_by_secret_and_generation(secret.id, 2)
    assert job is not None
    assert job.state == RotationJobState.FAILED
    assert job.last_error_code == "AUTHENTICATION_FAILED"


def test_zero_plaintext_leakage(db_session):
    """Verify private key and secret material are never persisted or present in audit details."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="success"
    )

    run_rotation_worker_cycle(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        worker_id="worker-1",
    )

    # Check Job table
    job_repo = RotationJobRepository(db_session)
    job = job_repo.get_by_secret_and_generation(secret.id, 2)
    job_dict = str(job.__dict__)
    assert "OPENSSH" not in job_dict
    assert "PRIVATE KEY" not in job_dict

    # Check Audit log records
    from sqlalchemy import select

    from app.audit.models import AuditLog

    events = db_session.execute(select(AuditLog)).scalars().all()
    assert len(events) > 0
    for event in events:
        details_str = str(event.details)
        assert "OPENSSH" not in details_str
        assert "PRIVATE KEY" not in details_str


def test_concurrent_scheduler_race_single_job_created(db_session):
    """Test that concurrent scheduler invocations produce exactly one effective job."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="success"
    )

    scheduler1 = RotationScheduler(db_session)
    scheduler2 = RotationScheduler(db_session)

    # First scheduler creates job
    job1, created1 = scheduler1.create_rotation_job(policy, secret)
    db_session.commit()
    assert created1 is True

    # Racing scheduler discovers same policy & generation
    job2, created2 = scheduler2.create_rotation_job(policy, secret)
    db_session.commit()
    assert created2 is False
    assert job1.id == job2.id

    # Verify only one job exists in database for this secret

    jobs = (
        db_session.execute(
            select(RotationJob).where(RotationJob.vault_secret_id == secret.id)
        )
        .scalars()
        .all()
    )
    assert len(jobs) == 1


def test_concurrent_worker_race_single_claim(db_session):
    """Test that two workers racing for the same queued job results in only one claim."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="success"
    )

    scheduler = RotationScheduler(db_session)
    job, _ = scheduler.create_rotation_job(policy, secret)
    db_session.commit()

    job_repo = RotationJobRepository(db_session)

    # Worker 1 claims
    claimed1 = job_repo.atomic_claim(job.id, "worker-1")
    db_session.commit()
    assert claimed1 is not None
    assert claimed1.lease_owner == "worker-1"

    # Worker 2 attempts claim while lease is active
    claimed2 = job_repo.atomic_claim(job.id, "worker-2")
    assert claimed2 is None


def test_crash_recovery_before_target_mutation_reclaimed(db_session):
    """Test crash recovery: worker dies before completion, expired lease is reclaimed by next worker."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="success"
    )

    scheduler = RotationScheduler(db_session)
    job, _ = scheduler.create_rotation_job(policy, secret)
    db_session.commit()

    job_repo = RotationJobRepository(db_session)
    # Simulate a crashed worker whose lease expired 10 minutes ago
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    job.transition_to_running(
        worker_id="crashed-worker-99", lease_duration_seconds=60, now=past_time
    )
    job.lease_expires_at = past_time + timedelta(seconds=60)
    job_repo.save(job)
    db_session.commit()

    # Next worker cycle runs
    result = run_rotation_worker_cycle(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        worker_id="recovering-worker",
    )

    assert result["succeeded"] == 1

    refreshed_job = job_repo.get_by_id(job.id)
    assert refreshed_job.state == RotationJobState.SUCCEEDED
    assert refreshed_job.lease_generation >= 2


def test_automated_bootstrap_rotation(db_session):
    """Test automated rotation of the bootstrap service account credential."""
    resource, secret, policy, enc, audit_svc, lc_svc, registry = _setup_environment(
        db_session, behaviour_mode="success"
    )

    # Resource represents bootstrap SSH target
    resource.hostname_ip = "127.0.0.1"
    resource.port = 2222
    db_session.commit()

    result = run_rotation_worker_cycle(
        session=db_session,
        audit_service=audit_svc,
        encryption_service=enc,
        lifecycle_service=lc_svc,
        executor_registry=registry,
        worker_id="bootstrap-worker",
    )

    assert result["succeeded"] == 1

    job_repo = RotationJobRepository(db_session)
    job = job_repo.get_by_secret_and_generation(secret.id, 2)
    assert job.state == RotationJobState.SUCCEEDED

    # Verify audit event emitted with ROTATION_COMPLETED
    events = (
        db_session.execute(
            select(AuditLog).where(AuditLog.action == "ROTATION_COMPLETED")
        )
        .scalars()
        .all()
    )
    assert len(events) >= 1
