"""Unit tests for RotationJob domain entity, state machine, and error sanitization."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.vault_lifecycle.rotation_job import (
    ACTIVE_JOB_STATES,
    SAFE_ERROR_CODES,
    TERMINAL_JOB_STATES,
    RotationJob,
    RotationJobState,
    sanitize_error_code,
    sanitize_error_message,
)


def test_rotation_job_creation_default_invariants():
    """Test initial attributes and default values of RotationJob."""
    secret_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    job = RotationJob(
        id=uuid.uuid4(),
        vault_secret_id=secret_id,
        resource_id=resource_id,
        rotation_generation=1,
        state=RotationJobState.QUEUED,
    )

    assert job.vault_secret_id == secret_id
    assert job.resource_id == resource_id
    assert job.rotation_generation == 1
    assert job.state == RotationJobState.QUEUED
    assert job.attempt_count == 0
    assert job.max_attempts == 3
    assert job.lease_owner is None
    assert job.lease_expires_at is None
    assert job.lease_generation == 0
    assert job.started_at is None
    assert job.completed_at is None
    assert job.is_lease_expired() is True


def test_rotation_job_claim_and_running_transition():
    """Test valid transition from QUEUED to RUNNING via transition_to_running."""
    job = RotationJob(
        id=uuid.uuid4(),
        vault_secret_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        rotation_generation=2,
        state=RotationJobState.QUEUED,
    )

    now = datetime.now(timezone.utc)
    job.transition_to_running(
        worker_id="worker-node-1", lease_duration_seconds=120, now=now
    )

    assert job.state == RotationJobState.RUNNING
    assert job.lease_owner == "worker-node-1"
    assert job.lease_generation == 1
    assert job.attempt_count == 1
    assert job.started_at == now
    assert job.lease_expires_at == now + timedelta(seconds=120)
    assert job.is_lease_expired(now + timedelta(seconds=60)) is False
    assert job.is_lease_expired(now + timedelta(seconds=121)) is True


def test_rotation_job_success_transition():
    """Test transition from RUNNING to SUCCEEDED."""
    job = RotationJob(
        id=uuid.uuid4(),
        vault_secret_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        rotation_generation=1,
        state=RotationJobState.RUNNING,
        lease_owner="worker-1",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        lease_generation=1,
        attempt_count=1,
    )

    now = datetime.now(timezone.utc)
    job.transition_to_succeeded(now=now)

    assert job.state == RotationJobState.SUCCEEDED
    assert job.completed_at == now
    assert job.lease_owner is None
    assert job.lease_expires_at is None
    assert job.state in TERMINAL_JOB_STATES


def test_rotation_job_retry_pending_transition():
    """Test transition from RUNNING to RETRY_PENDING."""
    job = RotationJob(
        id=uuid.uuid4(),
        vault_secret_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        rotation_generation=1,
        state=RotationJobState.RUNNING,
        lease_owner="worker-1",
        lease_generation=1,
        attempt_count=1,
    )

    now = datetime.now(timezone.utc)
    next_retry = now + timedelta(seconds=30)
    job.transition_to_retry_pending(
        next_retry_at=next_retry,
        error_code="SSH_TIMEOUT",
        error_classification="TIMEOUT",
        now=now,
    )

    assert job.state == RotationJobState.RETRY_PENDING
    assert job.next_retry_at == next_retry
    assert job.last_error_code == "SSH_TIMEOUT"
    assert job.last_error_classification == "TIMEOUT"
    assert job.lease_owner is None
    assert job.state in ACTIVE_JOB_STATES


def test_rotation_job_failed_transition():
    """Test transition from RUNNING to FAILED."""
    job = RotationJob(
        id=uuid.uuid4(),
        vault_secret_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        rotation_generation=1,
        state=RotationJobState.RUNNING,
        lease_owner="worker-1",
        lease_generation=1,
    )

    now = datetime.now(timezone.utc)
    job.transition_to_failed(
        error_code="HOST_KEY_MISMATCH",
        error_classification="SECURITY_FAILURE",
        now=now,
    )

    assert job.state == RotationJobState.FAILED
    assert job.completed_at == now
    assert job.last_error_code == "HOST_KEY_MISMATCH"
    assert job.last_error_classification == "SECURITY_FAILURE"
    assert job.lease_owner is None
    assert job.state in TERMINAL_JOB_STATES


def test_rotation_job_security_uncertainty_transition():
    """Test transition from RUNNING to SECURITY_UNCERTAINTY."""
    job = RotationJob(
        id=uuid.uuid4(),
        vault_secret_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        rotation_generation=1,
        state=RotationJobState.RUNNING,
        lease_owner="worker-1",
        lease_generation=1,
    )

    now = datetime.now(timezone.utc)
    job.transition_to_security_uncertainty(
        error_code="SECURITY_UNCERTAINTY",
        error_classification="UNCERTAIN_STATE",
        now=now,
    )

    assert job.state == RotationJobState.SECURITY_UNCERTAINTY
    assert job.completed_at == now
    assert job.last_error_code == "SECURITY_UNCERTAINTY"
    assert job.last_error_classification == "UNCERTAIN_STATE"
    assert job.lease_owner is None
    assert job.state in TERMINAL_JOB_STATES


def test_rotation_job_invalid_transitions():
    """Test that invalid state transitions raise ValueError."""
    job = RotationJob(
        id=uuid.uuid4(),
        vault_secret_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        rotation_generation=1,
        state=RotationJobState.SUCCEEDED,
    )

    with pytest.raises(ValueError, match="Cannot transition to RUNNING"):
        job.transition_to_running("worker-1")

    with pytest.raises(ValueError, match="Cannot complete job from state"):
        job.transition_to_succeeded()

    with pytest.raises(ValueError, match="Cannot schedule retry from state"):
        job.transition_to_retry_pending(
            datetime.now(timezone.utc) + timedelta(minutes=1), "SSH_TIMEOUT"
        )


def test_sanitize_error_code_allowlist():
    """Verify error code sanitization against the safe allowlist."""
    assert sanitize_error_code("ssh_timeout") == "SSH_TIMEOUT"
    assert sanitize_error_code("HOST_KEY_MISMATCH") == "HOST_KEY_MISMATCH"
    assert sanitize_error_code("cas_conflict") == "CAS_CONFLICT"
    assert sanitize_error_code("arbitrary_unknown_code") == "UNEXPECTED_ERROR"
    assert sanitize_error_code(None) == "UNEXPECTED_ERROR"
    for code in SAFE_ERROR_CODES:
        assert sanitize_error_code(code) == code


def test_sanitize_error_message_redaction():
    """Verify error messages strip plaintext key material and secret tokens."""
    leaked_msg = (
        "Error with private_key: -----BEGIN OPENSSH PRIVATE KEY----- bWFnaWM= "
        "and password=hunter2 during connect"
    )
    sanitized = sanitize_error_message(leaked_msg)
    assert "-----BEGIN OPENSSH" not in sanitized
    assert "hunter2" not in sanitized
    assert "[REDACTED]" in sanitized
