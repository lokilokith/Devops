"""Tests for ApprovalWorkflow Repository."""

import pytest

from app.approval_workflow.models import ApprovalLevel, ApprovalStatus, ApprovalWorkflow
from app.approval_workflow.repository import ApprovalWorkflowRepository


@pytest.fixture
def repo(db_session):
    return ApprovalWorkflowRepository(db_session)


@pytest.fixture
def test_user(db_session):
    from app.identity.models import User

    user = User(
        username="test_user",
        email="test@user.com",
        full_name="Test User",
        employee_id="T01",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_role(db_session):
    from app.roles.models import Role

    role = Role(role_code="TEST_ROLE", role_name="Test Role")
    db_session.add(role)
    db_session.commit()
    return role


@pytest.fixture
def sample_workflow(db_session, test_user, test_role):
    # Mock an access request because of foreign key constraint
    from app.access_requests.models import AccessRequest, AccessRequestPriority

    ar = AccessRequest(
        request_number="AR-TEST-001",
        requester_id=test_user.id,
        requested_role_id=test_role.id,
        business_justification="Test",
        priority=AccessRequestPriority.LOW,
    )
    db_session.add(ar)
    db_session.flush()

    wf = ApprovalWorkflow(
        access_request_id=ar.id,
        approver_id=test_user.id,
        approval_level=ApprovalLevel.MANAGER,
        status=ApprovalStatus.PENDING,
    )
    db_session.add(wf)
    db_session.commit()
    return wf


def test_create_workflow(repo, test_user, sample_workflow):
    assert sample_workflow.id is not None
    assert sample_workflow.status == ApprovalStatus.PENDING


def test_get_by_id(repo, sample_workflow):
    wf = repo.get_by_id(sample_workflow.id)
    assert wf is not None
    assert wf.id == sample_workflow.id


def test_update_workflow(repo, sample_workflow):
    sample_workflow.status = ApprovalStatus.APPROVED
    updated = repo.update_workflow(sample_workflow)
    assert updated.status == ApprovalStatus.APPROVED


def test_list_and_count(repo, sample_workflow):
    workflows = repo.list()
    assert len(workflows) > 0

    count = repo.count()
    assert count > 0


def test_filtering(repo, sample_workflow):
    workflows = repo.list(status="pending")
    assert len(workflows) == 1

    workflows_none = repo.list(status="approved")
    assert len(workflows_none) == 0


def test_pagination(repo, db_session, test_user, test_role, sample_workflow):
    workflows = repo.list(page=1, page_size=10)
    assert len(workflows) > 0
