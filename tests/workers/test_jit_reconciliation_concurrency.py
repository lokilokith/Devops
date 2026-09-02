from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select
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


class FakeExecutor:
    def inspect_target_state(self, request):
        return ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.INSPECT_TARGET_STATE,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={"sudoers_present": False, "active_sessions": []},
        )
    def terminate_jit_sessions(self, request):
        return ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.TERMINATE_JIT_SESSIONS,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={},
        )
    def revoke_jit_grant(self, request):
        return ExecutionResult(
            execution_id=request.execution_id,
            operation=ExecutionOperation.REVOKE_JIT_GRANT,
            status=ExecutionStatus.SUCCESS,
            verification_status=VerificationStatus.VERIFIED_SUCCESS,
            details={},
        )


@pytest.fixture
def mock_audit():
    return MagicMock(spec=AuditService)


@pytest.fixture
def target_repo(db_session):
    return TargetAccountBindingRepository(db_session)


@pytest.fixture
def test_grant(db_session):
    now = datetime.now(timezone.utc)
    from app.identity.models import User, UserStatus
    from app.resources.models import Environment, Resource, ResourceStatus, ResourceType
    from app.roles.models import Role
    from app.target_accounts.models import (
        TargetAccountBinding,
        TargetAccountBindingStatus,
    )

    user = User(
        id=uuid4(),
        employee_id=f"EMP-{uuid4().hex[:6]}",
        email=f"worker_user_{uuid4().hex[:8]}@example.com",
        username=f"u_{uuid4().hex[:8]}",
        full_name="Worker User",
        password_hash="pw",
        status=UserStatus.ACTIVE,
    )
    role = Role(
        role_code=f"P9_ROLE_{uuid4().hex[:6].upper()}",
        role_name=f"P9 Role {uuid4().hex[:6]}",
        description="test",
    )
    resource = Resource(
        resource_code=f"RES_{uuid4().hex[:6].upper()}",
        resource_name=f"Server {uuid4().hex[:6]}",
        resource_type=ResourceType.SERVER,
        status=ResourceStatus.ACTIVE,
        environment=Environment.DEV,
    )
    db_session.add_all([user, role, resource])
    db_session.flush()

    binding = TargetAccountBinding(
        control_plane_user_id=user.id,
        resource_id=resource.id,
        target_os_username=f"u_{user.username[:10]}",
        status=TargetAccountBindingStatus.ACTIVE,
    )
    db_session.add(binding)
    db_session.flush()

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


def test_concurrency_two_workers_claim(db_session: Session, test_grant, mock_audit, target_repo):
    """Test A: two reconciliation workers attempt to claim the same reconciliation row."""
    jit_access_repo = JITAccessRepository(db_session)
    w1 = JITReconciliationWorker(jit_access_repo, mock_audit, FakeExecutor(), target_repo, b"", "worker1")
    w2 = JITReconciliationWorker(jit_access_repo, mock_audit, FakeExecutor(), target_repo, b"", "worker2")

    claimed1 = w1.claim_next_batch(1)
    assert test_grant.id in claimed1

    # w2 should not claim it because it's already claimed and lease has not expired
    claimed2 = w2.claim_next_batch(1)
    assert test_grant.id not in claimed2

    state = db_session.execute(select(JITReconciliationState).filter_by(grant_id=test_grant.id)).scalar_one_or_none()
    assert state is not None
    assert state.worker_id == "worker1"

def test_concurrency_stale_worker(db_session: Session, test_grant, mock_audit, target_repo):
    """Test B: Worker A claims, lease expires, Worker B claims, Worker A attempts completion."""
    jit_access_repo = JITAccessRepository(db_session)
    w1 = JITReconciliationWorker(jit_access_repo, mock_audit, FakeExecutor(), target_repo, b"", "worker1")
    w2 = JITReconciliationWorker(jit_access_repo, mock_audit, FakeExecutor(), target_repo, b"", "worker2")

    w1.claim_next_batch(1)
    state = db_session.execute(select(JITReconciliationState).filter_by(grant_id=test_grant.id)).scalar_one_or_none()

    # Expire lease
    state.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.commit()

    # Worker B claims
    claimed2 = w2.claim_next_batch(1)
    assert test_grant.id in claimed2

    # Worker A attempts to commit
    w1._commit_reconciliation_state(test_grant.id, ReconciliationStatus.SYNCHRONIZED, "done")

    state = db_session.execute(select(JITReconciliationState).filter_by(grant_id=test_grant.id)).scalar_one_or_none()
    # Since w1._commit_reconciliation_state verifies worker_id before committing,
    # it remains worker2.
    assert state.worker_id == "worker2"

def test_crash_before_mutation(db_session: Session, test_grant, mock_audit, target_repo):
    """Test C: Worker claims and crashes, lease expires, another worker recovers."""
    jit_access_repo = JITAccessRepository(db_session)
    w1 = JITReconciliationWorker(jit_access_repo, mock_audit, FakeExecutor(), target_repo, b"", "worker1")
    w2 = JITReconciliationWorker(jit_access_repo, mock_audit, FakeExecutor(), target_repo, b"", "worker2")

    w1.claim_next_batch(1)
    # Simulate crash by expiring lease
    state = db_session.execute(select(JITReconciliationState).filter_by(grant_id=test_grant.id)).scalar_one_or_none()
    state.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    claimed2 = w2.claim_next_batch(1)
    assert test_grant.id in claimed2
