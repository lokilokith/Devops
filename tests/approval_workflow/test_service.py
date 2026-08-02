from uuid import uuid4

import pytest
from werkzeug.exceptions import Forbidden

from app.access_requests.models import AccessRequestStatus
from app.approval_workflow.exceptions import (
    ApprovalWorkflowInvalidStateError,
    ApprovalWorkflowValidationError,
)
from app.approval_workflow.models import ApprovalStatus
from app.user_roles.exceptions import UserRoleAlreadyExistsError


def test_create_initial_workflow(approval_service, sample_users, sample_request):
    u1, u2 = sample_users
    wf = approval_service.create_initial_workflow(sample_request.id, u2.id)
    assert wf.status == ApprovalStatus.PENDING
    assert wf.access_request_id == sample_request.id
    assert wf.approver_id == u2.id

    with pytest.raises(
        ApprovalWorkflowValidationError, match="Access request not found"
    ):
        approval_service.create_initial_workflow(uuid4(), u2.id)


def test_approve_workflow(
    approval_service,
    approval_repo,
    ar_repo,
    ur_repo,
    sample_users,
    sample_request,
    sample_role,
):
    u1, u2 = sample_users
    wf = approval_service.create_initial_workflow(sample_request.id, u2.id)

    # Approve
    approved_wf = approval_service.approve(wf.id, u2.id, "Approved")
    assert approved_wf.status == ApprovalStatus.APPROVED

    # Check access request updated
    req = ar_repo.get_by_id(sample_request.id)
    assert req.status == AccessRequestStatus.APPROVED

    # Check user role assigned
    lst = ur_repo.list_roles_for_user(u1.id)
    assert len(lst) == 1
    assert lst[0].id == sample_role.id

    # Test duplicate approval role assignment ignore
    # Actually wait, need a new request with the same role for duplicate. Or
    # just assign manually.
    with pytest.raises(UserRoleAlreadyExistsError):
        ur_repo.assign_role_to_user(
            user_id=u1.id, role_id=sample_role.id, assigned_by_user_id=u2.id
        )

    # Validation errors
    with pytest.raises(
        ApprovalWorkflowValidationError, match="Approval workflow not found"
    ):
        approval_service.approve(uuid4(), u2.id)

    with pytest.raises(
        ApprovalWorkflowInvalidStateError, match="Invalid transition from"
    ):
        approval_service.approve(wf.id, u2.id)

    wf3 = approval_service.create_initial_workflow(sample_request.id, u2.id)
    with pytest.raises(Forbidden, match="Approver mismatch"):
        approval_service.approve(wf3.id, u1.id)


def test_approve_duplicate_assignment_silent(
    approval_service, ur_repo, sample_users, sample_request, sample_role
):
    u1, u2 = sample_users
    wf = approval_service.create_initial_workflow(sample_request.id, u2.id)
    ur_repo.assign_role_to_user(
        user_id=u1.id, role_id=sample_role.id, assigned_by_user_id=u2.id
    )
    # The role is already assigned. Approval should not raise.
    approval_service.approve(wf.id, u2.id)  # Silent catch


def test_reject_workflow(approval_service, ar_repo, sample_users, sample_request):
    u1, u2 = sample_users
    wf = approval_service.create_initial_workflow(sample_request.id, u2.id)

    rejected_wf = approval_service.reject(wf.id, u2.id, "No")
    assert rejected_wf.status == ApprovalStatus.REJECTED

    req = ar_repo.get_by_id(sample_request.id)
    assert req.status == AccessRequestStatus.REJECTED

    # Validation errors
    with pytest.raises(
        ApprovalWorkflowValidationError, match="Approval workflow not found"
    ):
        approval_service.reject(uuid4(), u2.id)

    with pytest.raises(
        ApprovalWorkflowInvalidStateError, match="Invalid transition from"
    ):
        approval_service.reject(wf.id, u2.id)

    wf3 = approval_service.create_initial_workflow(sample_request.id, u2.id)
    with pytest.raises(Forbidden, match="Approver mismatch"):
        approval_service.reject(wf3.id, u1.id)


def test_cancel_workflow_for_request(
    approval_service, approval_repo, sample_users, sample_request
):
    u1, u2 = sample_users
    wf1 = approval_service.create_initial_workflow(sample_request.id, u2.id)

    approval_service.cancel_workflow_for_request(sample_request.id, "Cancelling")

    fetched = approval_repo.get_by_id(wf1.id)
    assert fetched.status == ApprovalStatus.CANCELLED
    assert fetched.comments == "Cancelling"
