from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.execution.domain import (
    ExecutionOperation,
    ExecutionResult,
    ExecutionStatus,
    VerificationStatus,
)
from app.jit_access.models import (
    JITAccessGrant,
    JITGrantStatus,
    JITReconciliationState,
    ReconciliationStatus,
)
from app.jit_access.repository import JITAccessRepository
from app.target_accounts.repository import TargetAccountBindingRepository
from app.workers.jit_reconciliation_worker import JITReconciliationWorker


class FailInspectExecutor:
    def inspect_target_state(self, request):
        return ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.INSPECT_TARGET_STATE,
            status=ExecutionStatus.FAILED,
            verification_status=VerificationStatus.UNVERIFIED,
            error_message="SSH Connection timeout",
            details=None
        )

class CrashCommitWorker(JITReconciliationWorker):
    def _commit_reconciliation_state(self, grant_id, status, reason):
        raise OperationalError("database is locked", None, None)

@pytest.fixture
def mock_audit():
    return MagicMock(spec=AuditService)

@pytest.fixture
def target_repo(db_session):
    return TargetAccountBindingRepository(db_session)

@pytest.fixture
def test_grant(db_session: Session):
    from app.identity.models import User
    from app.resources.models import Resource
    from app.roles.models import Role
    from app.target_accounts.models import TargetAccountBinding

    now = datetime.now(timezone.utc)
    user = User(employee_id="E123", username="test_user1", email="test1@example.com", full_name="Test User")
    role = Role(role_code="test1", role_name="test_role1", description="Test Role")
    resource = Resource(resource_code="res1", resource_name="test_resource1", resource_type="server")
    db_session.add_all([user, role, resource])
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(role)
    db_session.refresh(resource)

    from app.target_accounts.models import TargetAccountBindingStatus

    binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=resource.id,
        target_os_username="root",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add(binding)
    db_session.commit()
    db_session.refresh(binding)

    grant = JITAccessGrant(
        user_id=user.id,
        role_id=role.id,
        resource_id=resource.id,
        target_account_binding_id=binding.id,
        approval_request_id=uuid4(),
        command_set_id="system_health_check",
        status=JITGrantStatus.SECURITY_UNCERTAIN,
        expires_at=now + timedelta(hours=1),
        row_version=1,
    )
    db_session.add(grant)
    db_session.commit()
    db_session.refresh(grant)
    return grant

def test_ssh_failure_during_inspection(db_session: Session, test_grant, mock_audit, target_repo):
    jit_access_repo = JITAccessRepository(db_session)
    w = JITReconciliationWorker(jit_access_repo, mock_audit, FailInspectExecutor(), target_repo, b"")

    # Run process_reconciliation
    results = w.process_reconciliation()

    assert len(results) == 1
    print("RESULTS:", results)
    # Because classify_target_state handles None target_data, it returns FAILED if there's no data for an expected state.
    # Actually wait, classification of UNCERTAIN with None data -> SECURITY_UNCERTAIN (FAILED)
    state = db_session.execute(select(JITReconciliationState).filter_by(grant_id=test_grant.id)).scalar_one_or_none()
    assert state.status == ReconciliationStatus.UNREACHABLE
    assert "unreachable" in state.failure_reason.lower()

def test_db_disconnect_mid_reconciliation(db_session: Session, test_grant, mock_audit, target_repo):
    jit_access_repo = JITAccessRepository(db_session)
    w = CrashCommitWorker(jit_access_repo, mock_audit, FailInspectExecutor(), target_repo, b"")

    results = w.process_reconciliation()

    # Process should catch the error and try to rollback and mark as failed.
    # But wait, if _fail_reconciliation also calls _commit_reconciliation_state, it will also raise OperationalError.
    # The worker handles exceptions in the loop:
    # try:
    #     res = self._reconcile_single_grant(grant_id)
    # except Exception as e:
    #     self._fail_reconciliation(grant_id, str(e))
    # _fail_reconciliation catches exception and rolls back!

    assert len(results) == 1
    assert "error" in results[0]["status"]
    assert "database is locked" in results[0]["error"]
