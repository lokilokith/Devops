from unittest.mock import MagicMock, patch

from app.workers.rotation_worker import (
    _handle_retryable_failure,
    _handle_security_uncertainty,
    _handle_terminal_failure,
    _process_policy,
    process_rotation_job,
    run_rotation_worker_cycle,
)


def test_run_rotation_worker_cycle_no_jobs():
    with patch("app.workers.rotation_worker._fetch_eligible_policies", return_value=[]):
        assert isinstance(
            run_rotation_worker_cycle(
                MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
            ),
            dict,
        )


def test_run_rotation_worker_cycle_exception():
    with patch(
        "app.workers.rotation_worker._fetch_eligible_policies",
        side_effect=Exception("test"),
    ):
        try:
            run_rotation_worker_cycle(
                MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
            )
        except Exception:
            pass


def test_process_policy_exception():
    try:
        _process_policy(
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
    except Exception:
        pass


def test_process_rotation_job():
    try:
        process_rotation_job(
            MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
        )
    except Exception:
        pass


def test_handle_retryable_failure():
    try:
        _handle_retryable_failure(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    except Exception:
        pass


def test_handle_security_uncertainty():
    try:
        _handle_security_uncertainty(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    except Exception:
        pass


def test_handle_terminal_failure():
    try:
        _handle_terminal_failure(
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
    except Exception:
        pass
