import pytest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.approval_workflow.models import ApprovalWorkflow, ApprovalStatus, ApprovalLevel
from app.approval_workflow.exceptions import (
    ApprovalWorkflowNotFoundError,
    ApprovalWorkflowRepositoryError,
)

def test_create_and_get(approval_repo, sample_users, sample_request):
    u1, u2 = sample_users
    wf = ApprovalWorkflow(
        access_request_id=sample_request.id,
        approver_id=u2.id,
        approval_level=ApprovalLevel.MANAGER,
        status=ApprovalStatus.PENDING
    )
    created = approval_repo.create_workflow(wf)
    assert created.id is not None

    fetched = approval_repo.get_by_id(created.id)
    assert fetched.approver_id == u2.id
    
    req_wfs = approval_repo.get_by_request(sample_request.id)
    assert len(req_wfs) == 1
    assert req_wfs[0].id == created.id

def test_approve_reject_cancel(approval_repo, sample_users, sample_request):
    u1, u2 = sample_users
    
    wf1 = approval_repo.create_workflow(ApprovalWorkflow(
        access_request_id=sample_request.id, approver_id=u2.id, approval_level=ApprovalLevel.MANAGER
    ))
    approved = approval_repo.approve(wf1.id, "Looks good")
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.comments == "Looks good"
    assert approved.approved_at is not None

    wf2 = approval_repo.create_workflow(ApprovalWorkflow(
        access_request_id=sample_request.id, approver_id=u2.id, approval_level=ApprovalLevel.MANAGER
    ))
    rejected = approval_repo.reject(wf2.id, "No")
    assert rejected.status == ApprovalStatus.REJECTED
    assert rejected.comments == "No"

    wf3 = approval_repo.create_workflow(ApprovalWorkflow(
        access_request_id=sample_request.id, approver_id=u2.id, approval_level=ApprovalLevel.MANAGER
    ))
    cancelled = approval_repo.cancel(wf3.id, "Cancelled")
    assert cancelled.status == ApprovalStatus.CANCELLED
    assert cancelled.comments == "Cancelled"

def test_list_and_count(approval_repo, sample_users, sample_request):
    u1, u2 = sample_users
    approval_repo.create_workflow(ApprovalWorkflow(
        access_request_id=sample_request.id, approver_id=u2.id, approval_level=ApprovalLevel.MANAGER
    ))
    
    assert approval_repo.count() >= 1
    lst = approval_repo.list()
    assert len(lst) >= 1
    
    pending = approval_repo.list_pending()
    assert len(pending) >= 1

def test_not_found(approval_repo):
    with pytest.raises(ApprovalWorkflowNotFoundError):
        approval_repo.approve(uuid4(), "test")
    with pytest.raises(ApprovalWorkflowNotFoundError):
        approval_repo.reject(uuid4(), "test")
    with pytest.raises(ApprovalWorkflowNotFoundError):
        approval_repo.cancel(uuid4(), "test")

def test_sqlalchemy_errors(approval_repo, sample_users, sample_request):
    u1, u2 = sample_users
    wf = ApprovalWorkflow(
        access_request_id=sample_request.id,
        approver_id=u2.id,
        approval_level=ApprovalLevel.MANAGER,
    )

    with patch.object(approval_repo._session, 'add', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.create_workflow(wf)
            
    with patch.object(approval_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.get_by_id(uuid4())

    with patch.object(approval_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.get_by_request(uuid4())

    with patch.object(approval_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.list_pending()

    with patch.object(approval_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.list()

    with patch.object(approval_repo._session, 'execute', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.count()

    wf2 = approval_repo.create_workflow(ApprovalWorkflow(
        access_request_id=sample_request.id, approver_id=u2.id, approval_level=ApprovalLevel.MANAGER
    ))

    with patch.object(approval_repo._session, 'commit', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.approve(wf2.id)

    with patch.object(approval_repo._session, 'commit', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.reject(wf2.id)

    with patch.object(approval_repo._session, 'commit', side_effect=SQLAlchemyError("mocked error")):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.cancel(wf2.id)
