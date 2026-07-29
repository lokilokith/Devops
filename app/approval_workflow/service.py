"""ApprovalWorkflow Service for OpsForge."""
from __future__ import annotations
from typing import Sequence, Any
from uuid import UUID

from app.approval_workflow.models import ApprovalWorkflow, ApprovalStatus, ApprovalLevel
from app.approval_workflow.repository import ApprovalWorkflowRepository
from app.approval_workflow.exceptions import (
    ApprovalWorkflowInvalidStateError,
    ApprovalWorkflowValidationError,
)
from app.access_requests.repository import AccessRequestRepository
from app.access_requests.models import AccessRequestStatus
from app.user_roles.repository import UserRolesRepository
from app.user_roles.exceptions import UserRoleAlreadyExistsError

class ApprovalWorkflowService:
    def __init__(
        self,
        approval_repo: ApprovalWorkflowRepository,
        access_request_repo: AccessRequestRepository,
        user_roles_repo: UserRolesRepository,
    ) -> None:
        self._repo = approval_repo
        self._ar_repo = access_request_repo
        self._ur_repo = user_roles_repo

    def create_initial_workflow(
        self,
        access_request_id: UUID,
        approver_id: UUID,
        level: ApprovalLevel = ApprovalLevel.MANAGER
    ) -> ApprovalWorkflow:
        req = self._ar_repo.get_by_id(access_request_id)
        if not req:
            raise ApprovalWorkflowValidationError("Access request not found.")
        wf = ApprovalWorkflow(
            access_request_id=access_request_id,
            approver_id=approver_id,
            approval_level=level,
            status=ApprovalStatus.PENDING,
        )
        return self._repo.create_workflow(wf)

    def approve(self, workflow_id: UUID, approver_id: UUID, comments: str | None = None) -> ApprovalWorkflow:
        wf = self._repo.get_by_id(workflow_id)
        if not wf:
            raise ApprovalWorkflowValidationError("Approval workflow not found.")
        if wf.status != ApprovalStatus.PENDING:
            raise ApprovalWorkflowInvalidStateError("Only pending workflows can be approved.")
        if wf.approver_id != approver_id:
            raise ApprovalWorkflowValidationError("Approver mismatch.")

        approved_wf = self._repo.approve(workflow_id, comments)

        # Update Access Request and Assign Roles
        req = self._ar_repo.get_by_id(wf.access_request_id)
        if req:
            self._ar_repo.approve(req.id, approver_id)
            if req.requested_role_id:
                try:
                    self._ur_repo.assign_role_to_user(
                        user_id=req.requester_id,
                        role_id=req.requested_role_id,
                        assigned_by_user_id=approver_id
                    )
                except UserRoleAlreadyExistsError:
                    pass
        return approved_wf

    def reject(self, workflow_id: UUID, rejecter_id: UUID, comments: str | None = None) -> ApprovalWorkflow:
        wf = self._repo.get_by_id(workflow_id)
        if not wf:
            raise ApprovalWorkflowValidationError("Approval workflow not found.")
        if wf.status != ApprovalStatus.PENDING:
            raise ApprovalWorkflowInvalidStateError("Only pending workflows can be rejected.")
        if wf.approver_id != rejecter_id:
            raise ApprovalWorkflowValidationError("Approver mismatch.")

        rejected_wf = self._repo.reject(workflow_id, comments)

        # Update Access Request
        req = self._ar_repo.get_by_id(wf.access_request_id)
        if req:
            self._ar_repo.reject(req.id, reason=comments or "Rejected by workflow", rejecter_id=rejecter_id)
        return rejected_wf

    def cancel_workflow_for_request(self, access_request_id: UUID, comments: str | None = None) -> None:
        """Cancel pending approvals for a request."""
        workflows = self._repo.get_by_request(access_request_id)
        for wf in workflows:
            if wf.status == ApprovalStatus.PENDING:
                self._repo.cancel(wf.id, comments)

__all__ = ["ApprovalWorkflowService"]
