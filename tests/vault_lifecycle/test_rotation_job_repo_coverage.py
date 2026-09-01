import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.vault_lifecycle.rotation_job import RotationJobState
from app.vault_lifecycle.rotation_job_repository import RotationJobRepository


def test_rotation_job_repo_save_new():
    session = MagicMock()
    repo = RotationJobRepository(session)
    job = MagicMock()
    session.new = [job]
    res = repo.save(job)
    assert res == job
    session.add.assert_called_once_with(job)


def test_rotation_job_repo_atomic_claim_not_found():
    session = MagicMock()
    repo = RotationJobRepository(session)
    repo.get_by_id = MagicMock(return_value=None)
    res = repo.atomic_claim(uuid.uuid4(), "worker")
    assert res is None


def test_rotation_job_repo_atomic_claim_retry_pending_future():
    session = MagicMock()
    repo = RotationJobRepository(session)
    job = MagicMock()
    job.state = RotationJobState.RETRY_PENDING
    job.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    repo.get_by_id = MagicMock(return_value=job)
    res = repo.atomic_claim(uuid.uuid4(), "worker")
    assert res is None


def test_rotation_job_repo_atomic_claim_succeeded():
    session = MagicMock()
    repo = RotationJobRepository(session)
    job = MagicMock()
    job.state = RotationJobState.SUCCEEDED
    repo.get_by_id = MagicMock(return_value=job)
    res = repo.atomic_claim(uuid.uuid4(), "worker")
    assert res is None


def test_rotation_job_repo_atomic_claim_collision():
    session = MagicMock()
    repo = RotationJobRepository(session)
    job = MagicMock()
    job.state = RotationJobState.QUEUED
    job.row_version = 1
    job.lease_generation = 0
    job.attempt_count = 0
    repo.get_by_id = MagicMock(return_value=job)

    result = MagicMock()
    result.rowcount = 0
    session.execute.return_value = result

    res = repo.atomic_claim(uuid.uuid4(), "worker")
    assert res is None
