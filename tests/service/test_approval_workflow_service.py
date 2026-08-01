"""Tests for ApprovalWorkflow Service."""

import pytest
from uuid import uuid4
from unittest.mock import Mock, MagicMock

from app.approval_workflow.service import ApprovalWorkflowService
from app.approval_workflow.models import ApprovalWorkflow, ApprovalStatus, ApprovalLevel
from app.approval_workflow.exceptions import ApprovalWorkflowInvalidStateError
from app.audit.models import AuditStatus


@pytest.fixture
def service():
    approval_repo = Mock()
    access_request_repo = Mock()
    user_roles_repo = Mock()
    audit_service = Mock()
    session = Mock()
    return ApprovalWorkflowService(
        approval_repo, access_request_repo, user_roles_repo, audit_service, session
    )


def test_approve_workflow_success(service):
    wf_id = uuid4()
    approver_id = uuid4()
    req_id = uuid4()

    wf = ApprovalWorkflow(
        id=wf_id,
        status=ApprovalStatus.PENDING,
        approver_id=approver_id,
        access_request_id=req_id,
    )
    service._repo.get_by_id.return_value = wf
    service._ar_repo.get_by_id.return_value = Mock(
        id=req_id, requested_role_id=uuid4(), requester_id=uuid4()
    )

    approved_wf = service.approve(wf_id, approver_id)

    assert approved_wf.status == ApprovalStatus.APPROVED
    service._session.commit.assert_called_once()
    service._audit.log_event.assert_called_once()


def test_reject_workflow_success(service):
    wf_id = uuid4()
    rejecter_id = uuid4()
    req_id = uuid4()

    wf = ApprovalWorkflow(
        id=wf_id,
        status=ApprovalStatus.PENDING,
        approver_id=rejecter_id,
        access_request_id=req_id,
    )
    service._repo.get_by_id.return_value = wf
    service._ar_repo.get_by_id.return_value = Mock(
        id=req_id, requested_role_id=uuid4(), requester_id=uuid4()
    )

    rejected_wf = service.reject(wf_id, rejecter_id)

    assert rejected_wf.status == ApprovalStatus.REJECTED
    service._session.commit.assert_called_once()
    service._audit.log_event.assert_called_once()


def test_invalid_state_transition(service):
    wf_id = uuid4()
    approver_id = uuid4()

    # Already approved workflow
    wf = ApprovalWorkflow(
        id=wf_id, status=ApprovalStatus.APPROVED, approver_id=approver_id
    )
    service._repo.get_by_id.return_value = wf

    with pytest.raises(ApprovalWorkflowInvalidStateError):
        service.approve(wf_id, approver_id)

    service._session.commit.assert_not_called()


def test_transaction_rollback_on_error(service):
    wf_id = uuid4()
    approver_id = uuid4()
    req_id = uuid4()

    wf = ApprovalWorkflow(
        id=wf_id,
        status=ApprovalStatus.PENDING,
        approver_id=approver_id,
        access_request_id=req_id,
    )
    service._repo.get_by_id.return_value = wf

    # Force a failure during update
    service._repo.update_workflow.side_effect = Exception("DB error")

    with pytest.raises(Exception):
        service.approve(wf_id, approver_id)

    service._session.rollback.assert_called_once()
    service._session.commit.assert_not_called()
