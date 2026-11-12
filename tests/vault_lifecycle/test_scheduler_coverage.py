from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.vault_lifecycle.scheduler import RotationScheduler


def test_scheduler_idempotent_enqueue_integrity_error():
    session_mock = MagicMock()
    scheduler = RotationScheduler(session_mock)

    session_mock.add.side_effect = IntegrityError("error", "params", "orig")
    existing_job = MagicMock()
    scheduler._job_repo = MagicMock()
    scheduler._secret_repo = MagicMock()
    secret_aggregate = MagicMock()
    secret_aggregate.versions = []
    scheduler._secret_repo.find_by_id.return_value = secret_aggregate

    # Mocking get_by_secret_and_generation to return None the first time (to pass the first check)
    # and existing_job the second time (when caught in except IntegrityError)
    scheduler._job_repo.get_by_secret_and_generation.side_effect = [None, existing_job]

    secret_model = MagicMock()
    policy = MagicMock()

    job, created = scheduler.create_rotation_job(policy, secret_model)

    assert job == existing_job
    assert created is False
    session_mock.begin_nested.return_value.rollback.assert_called_once()
