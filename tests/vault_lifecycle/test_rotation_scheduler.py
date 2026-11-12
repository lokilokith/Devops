"""Unit and concurrency tests for RotationScheduler and due-detection engine."""

import uuid
from datetime import datetime, timedelta, timezone

from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.resources.models import (
    Criticality,
    Environment,
    Resource,
    ResourceStatus,
    ResourceType,
)
from app.vault.crypto import EncryptionService, LocalKMSProvider
from app.vault.domain import SecretFactory, SecretStatus, SecretVersion
from app.vault.repository import SqlAlchemyVaultRepository
from app.vault_lifecycle.models import (
    RotationJobState,
    RotationStatus,
    SecretRotationPolicy,
)
from app.vault_lifecycle.rotation_job import RotationJob
from app.vault_lifecycle.rotation_job_repository import RotationJobRepository
from app.vault_lifecycle.scheduler import RotationScheduler


def _setup_resource_and_secret(db_session, status=SecretStatus.ACTIVE):
    """Helper to persist a Resource and VaultSecret with one version."""
    resource = Resource(
        resource_code=f"SCH{uuid.uuid4().hex[:6].upper()}",
        resource_name=f"Scheduler Test Resource {uuid.uuid4().hex[:8]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
        criticality=Criticality.LOW,
    )
    db_session.add(resource)
    db_session.flush()

    kms = LocalKMSProvider()
    enc = EncryptionService(kms)
    sec_repo = SqlAlchemyVaultRepository(db_session)
    secret = SecretFactory.create_new_secret(resource.id)
    secret.status = status

    dek, payload, meta = enc.encrypt_payload(
        resource.id, secret.id, b"INITIAL_SECRET_DATA"
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
    secret.status = status
    sec_repo.save(secret)
    db_session.flush()
    return resource, secret


def test_discover_due_policies(db_session):
    """Verify discover_due_policies returns only active policies whose next_rotation_at <= now."""
    resource, secret1 = _setup_resource_and_secret(db_session)
    _, secret2 = _setup_resource_and_secret(db_session)
    _, secret3 = _setup_resource_and_secret(db_session)

    now = datetime.now(timezone.utc)

    # Due policy
    pol1 = SecretRotationPolicy(
        vault_secret_id=secret1.id,
        rotation_interval_seconds=3600,
        next_rotation_at=now - timedelta(minutes=5),
        status=RotationStatus.ACTIVE,
    )
    # Future policy (not due)
    pol2 = SecretRotationPolicy(
        vault_secret_id=secret2.id,
        rotation_interval_seconds=3600,
        next_rotation_at=now + timedelta(hours=1),
        status=RotationStatus.ACTIVE,
    )
    # Paused policy (due time passed but paused)
    pol3 = SecretRotationPolicy(
        vault_secret_id=secret3.id,
        rotation_interval_seconds=3600,
        next_rotation_at=now - timedelta(minutes=10),
        status=RotationStatus.PAUSED,
    )

    db_session.add_all([pol1, pol2, pol3])
    db_session.commit()

    scheduler = RotationScheduler(db_session)
    due = scheduler.discover_due_policies(now)

    assert len(due) == 1
    assert due[0].vault_secret_id == secret1.id


def test_eligibility_fails_closed(db_session):
    """Verify eligibility checks fail closed on invalid, checked_out, or conflicting state."""
    resource, secret = _setup_resource_and_secret(db_session)
    scheduler = RotationScheduler(db_session)

    policy = SecretRotationPolicy(
        vault_secret_id=secret.id,
        rotation_interval_seconds=3600,
        next_rotation_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        status=RotationStatus.ACTIVE,
    )
    db_session.add(policy)
    db_session.commit()

    # 1. Happy path -> eligible
    is_eligible, reason, sec_model = scheduler.verify_eligibility(policy)
    assert is_eligible is True
    assert reason is None
    assert sec_model is not None

    # 2. Secret status is CHECKED_OUT -> ineligible
    sec_model.status = SecretStatus.CHECKED_OUT
    db_session.commit()
    is_eligible, reason, _ = scheduler.verify_eligibility(policy)
    assert is_eligible is False
    assert "checked_out" in reason.lower()

    # 3. Secret status is ROTATING -> ineligible
    sec_model.status = SecretStatus.ROTATING
    db_session.commit()
    is_eligible, reason, _ = scheduler.verify_eligibility(policy)
    assert is_eligible is False
    assert "rotating" in reason.lower()

    # 4. Secret status is DESYNCED -> ineligible
    sec_model.status = SecretStatus.DESYNCED
    db_session.commit()
    is_eligible, reason, _ = scheduler.verify_eligibility(policy)
    assert is_eligible is False
    assert "desynced" in reason.lower()

    # Restore ACTIVE status
    sec_model.status = SecretStatus.ACTIVE
    db_session.commit()

    # 5. Existing active job in QUEUED state -> ineligible
    job = RotationJob(
        id=uuid.uuid4(),
        vault_secret_id=secret.id,
        resource_id=resource.id,
        rotation_generation=2,
        state=RotationJobState.QUEUED,
    )
    db_session.add(job)
    db_session.commit()

    is_eligible, reason, _ = scheduler.verify_eligibility(policy)
    assert is_eligible is False
    assert "already has an active rotation job" in reason


def test_idempotent_job_creation(db_session):
    """Verify create_rotation_job creates only one job per secret generation."""
    resource, secret = _setup_resource_and_secret(db_session)
    scheduler = RotationScheduler(db_session)

    policy = SecretRotationPolicy(
        vault_secret_id=secret.id,
        rotation_interval_seconds=3600,
        next_rotation_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        status=RotationStatus.ACTIVE,
    )
    db_session.add(policy)
    db_session.commit()

    # First creation
    job1, created1 = scheduler.create_rotation_job(policy, secret)
    db_session.commit()
    assert created1 is True
    assert job1 is not None
    assert job1.rotation_generation == 2
    assert job1.state == RotationJobState.QUEUED

    # Second creation attempt for same generation -> returns existing job
    job2, created2 = scheduler.create_rotation_job(policy, secret)
    assert created2 is False
    assert job2.id == job1.id


def test_scheduler_cycle_audit_logging(db_session):
    """Verify run_scheduler_cycle emits ROTATION_QUEUED audit events."""
    resource, secret = _setup_resource_and_secret(db_session)
    audit_repo = AuditRepository(db_session)
    audit_svc = AuditService(audit_repo)

    now = datetime.now(timezone.utc)
    policy = SecretRotationPolicy(
        vault_secret_id=secret.id,
        rotation_interval_seconds=3600,
        next_rotation_at=now - timedelta(seconds=10),
        status=RotationStatus.ACTIVE,
    )
    db_session.add(policy)
    db_session.commit()

    scheduler = RotationScheduler(db_session)
    metrics = scheduler.run_scheduler_cycle(audit_service=audit_svc, current_time=now)

    assert metrics["discovered_due"] == 1
    assert metrics["jobs_queued"] == 1
    assert metrics["ineligible_skipped"] == 0

    job_repo = RotationJobRepository(db_session)
    active_job = job_repo.get_active_job_for_secret(secret.id)
    assert active_job is not None
    assert active_job.state == RotationJobState.QUEUED
