import uuid
from unittest.mock import Mock

import pytest

from app.execution.domain import ExecutionResult, ExecutionStatus
from app.jit_access.models import (
    JITAccessGrant,
    JITGrantStatus,
    JITReconciliationState,
)
from app.target_accounts.models import TargetAccountBinding
from app.workers.jit_reconciliation_worker import JITReconciliationWorker


@pytest.fixture
def mock_session():
    return Mock()


@pytest.fixture
def mock_repo():
    return Mock()


@pytest.fixture
def mock_executor():
    return Mock()


@pytest.fixture
def worker(mock_session, mock_repo, mock_executor):
    mock_repo_wrapper = Mock()
    mock_repo_wrapper.session = mock_session
    w = JITReconciliationWorker(
        repository=mock_repo_wrapper,
        audit_service=Mock(),
        executor=mock_executor,
        target_account_repo=mock_repo,
        bootstrap_credential=b"test-bootstrap",
    )
    return w


def test_missing_target_os_username(worker, mock_session, mock_repo):
    grant = JITAccessGrant(id=uuid.uuid4(), status=JITGrantStatus.ACTIVE)
    mock_session.get.return_value = grant
    # Repo returns None binding
    mock_repo.get_by_id.return_value = None

    result = worker._reconcile_single_grant(grant.id)
    assert result["error"] == "Target OS username missing"


def test_safe_retry_execution(worker, mock_session, mock_repo, mock_executor):
    grant = JITAccessGrant(
        id=uuid.uuid4(),
        status=JITGrantStatus.REVOKED,
        target_account_binding_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )
    binding = TargetAccountBinding(
        id=grant.target_account_binding_id, target_os_username="root"
    )

    # DB lookups
    mock_session.get.return_value = grant
    mock_session.execute.return_value.scalar_one_or_none.return_value = (
        JITReconciliationState(worker_id=worker.worker_id)
    )
    mock_repo.get_by_id.return_value = binding

    # Mock inspect target state (trigger SAFE_RETRY)
    mock_executor.inspect_target_state.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation="test",
        verification_status=None,
        status=ExecutionStatus.SUCCESS,
        details={"sudoers_present": True, "active_sessions": []},
    )

    # Mock remediation (terminate + revoke)
    mock_executor.terminate_jit_sessions.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation="test",
        verification_status=None,
        status=ExecutionStatus.SUCCESS,
    )
    mock_executor.revoke_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation="test",
        verification_status=None,
        status=ExecutionStatus.SUCCESS,
    )

    result = worker._reconcile_single_grant(grant.id)
    print("DEBUG RESULT:", result)

    assert mock_executor.terminate_jit_sessions.called
    assert mock_executor.revoke_jit_grant.called
    assert result["remediation_performed"] is True


def test_safe_retry_execution_failure(worker, mock_session, mock_repo, mock_executor):
    grant = JITAccessGrant(
        id=uuid.uuid4(),
        status=JITGrantStatus.REVOKED,
        target_account_binding_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )
    binding = TargetAccountBinding(
        id=grant.target_account_binding_id, target_os_username="root"
    )

    mock_session.get.return_value = grant
    mock_session.execute.return_value.scalar_one_or_none.return_value = (
        JITReconciliationState(worker_id=worker.worker_id)
    )
    mock_repo.get_by_id.return_value = binding

    # Mock inspect target state (trigger SAFE_RETRY)
    mock_executor.inspect_target_state.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation="test",
        verification_status=None,
        status=ExecutionStatus.SUCCESS,
        details={"sudoers_present": True, "active_sessions": []},
    )

    mock_executor.terminate_jit_sessions.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation="test",
        verification_status=None,
        status=ExecutionStatus.SUCCESS,
    )
    mock_executor.revoke_jit_grant.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation="test",
        verification_status=None,
        status=ExecutionStatus.FAILED,
        error_message="SSH Fail",
    )

    with pytest.raises(Exception, match="Remediation failed: SSH Fail"):
        worker._reconcile_single_grant(grant.id)


def test_security_uncertain_recovery(worker, mock_session, mock_repo, mock_executor):
    grant = JITAccessGrant(
        id=uuid.uuid4(),
        status=JITGrantStatus.SECURITY_UNCERTAIN,
        target_account_binding_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        row_version=1,
    )
    binding = TargetAccountBinding(
        id=grant.target_account_binding_id, target_os_username="root"
    )

    # DB lookups
    mock_session.get.return_value = grant
    mock_session.execute.return_value.scalar_one_or_none.return_value = (
        JITReconciliationState(worker_id=worker.worker_id)
    )
    mock_repo.get_by_id.return_value = binding

    # Inspect -> SYNCHRONIZED
    mock_executor.inspect_target_state.return_value = ExecutionResult(
        execution_id=uuid.uuid4(),
        operation="test",
        verification_status=None,
        status=ExecutionStatus.SUCCESS,
        details={"sudoers_present": False, "active_sessions": []},
    )

    result = worker._reconcile_single_grant(grant.id)

    # Verify _recover_db_terminal_state was executed
    assert grant.status == JITGrantStatus.REVOKED
    assert grant.row_version == 2
    mock_session.add.assert_any_call(grant)
    assert (
        result["reason"]
        == "Uncertain grant proved cleanly removed (Recovered from SECURITY_UNCERTAIN to REVOKED)"
    )


def test_claim_failure(worker, mock_session):
    # If session.execute raises Exception
    mock_session.execute.side_effect = Exception("DB Error")
    with pytest.raises(Exception):
        worker.claim_next_batch(limit=10)
