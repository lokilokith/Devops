"""Tests for expiration worker exception handling."""

from unittest.mock import MagicMock

import pytest

from app.workers.expiration_worker import run_expiration_job


def test_run_expiration_job_catastrophic_failure():
    session = MagicMock()
    checkout_svc = MagicMock()
    checkout_svc.process_expirations.side_effect = RuntimeError("Database crash")

    with pytest.raises(RuntimeError, match="Database crash"):
        run_expiration_job(session, checkout_svc)
