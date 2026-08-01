from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.approval_workflow.exceptions import (
    ApprovalWorkflowNotFoundError,
    ApprovalWorkflowRepositoryError,
)
from app.approval_workflow.models import ApprovalLevel, ApprovalStatus, ApprovalWorkflow


def test_create_and_get(approval_repo, sample_users, sample_request):
    u1, u2 = sample_users
    wf = ApprovalWorkflow(
        access_request_id=sample_request.id,
        approver_id=u2.id,
        approval_level=ApprovalLevel.MANAGER,
        status=ApprovalStatus.PENDING,
    )
    created = approval_repo.create_workflow(wf)
    assert created.id is not None

    fetched = approval_repo.get_by_id(created.id)
    assert fetched.approver_id == u2.id

    req_wfs = approval_repo.get_by_request(sample_request.id)
    assert len(req_wfs) == 1
    assert req_wfs[0].id == created.id


def test_update_workflow(approval_repo, sample_users, sample_request):
    u1, u2 = sample_users

    wf1 = approval_repo.create_workflow(
        ApprovalWorkflow(
            access_request_id=sample_request.id,
            approver_id=u2.id,
            approval_level=ApprovalLevel.MANAGER,
        )
    )
    wf1.status = ApprovalStatus.APPROVED
    wf1.comments = "Looks good"
    approved = approval_repo.update_workflow(wf1)

    assert approved.status == ApprovalStatus.APPROVED
    assert approved.comments == "Looks good"


def test_list_and_count(approval_repo, sample_users, sample_request):
    u1, u2 = sample_users
    approval_repo.create_workflow(
        ApprovalWorkflow(
            access_request_id=sample_request.id,
            approver_id=u2.id,
            approval_level=ApprovalLevel.MANAGER,
        )
    )

    assert approval_repo.count() >= 1
    lst = approval_repo.list()
    assert len(lst) >= 1


def test_sqlalchemy_errors(approval_repo, sample_users, sample_request):
    u1, u2 = sample_users
    wf = ApprovalWorkflow(
        access_request_id=sample_request.id,
        approver_id=u2.id,
        approval_level=ApprovalLevel.MANAGER,
    )

    with patch.object(
        approval_repo._session, "add", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.create_workflow(wf)

    with patch.object(
        approval_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.get_by_id(uuid4())

    with patch.object(
        approval_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.get_by_request(uuid4())

    with patch.object(
        approval_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.list()

    with patch.object(
        approval_repo._session, "execute", side_effect=SQLAlchemyError("mocked error")
    ):
        with pytest.raises(ApprovalWorkflowRepositoryError):
            approval_repo.count()
