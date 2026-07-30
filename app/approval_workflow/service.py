"""ApprovalWorkflow Service for OpsForge."""
from __future__ import annotations
from typing import Sequence, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.approval_workflow.models import ApprovalWorkflow, ApprovalStatus, ApprovalLevel
from app.approval_workflow.repository import ApprovalWorkflowRepository
from app.approval_workflow.validators import validate_state_transition
from app.approval_workflow.exceptions import (
    ApprovalWorkflowInvalidStateError,
    ApprovalWorkflowValidationError,
)
from app.notifications.events import approval_required, workflow_failed
from app.access_requests.repository import AccessRequestRepository
from app.access_requests.models import AccessRequestStatus
from app.user_roles.repository import UserRolesRepository
from app.user_roles.exceptions import UserRoleAlreadyExistsError
from app.audit.service import AuditService
from app.audit.models import AuditStatus, AuditSeverity

class ApprovalWorkflowService:
    def __init__(
        self,
        approval_repo: ApprovalWorkflowRepository,
        access_request_repo: AccessRequestRepository,
        user_roles_repo: UserRolesRepository,
        audit_service: AuditService,
        session: Session,
    ) -> None:
        self._repo = approval_repo
        self._ar_repo = access_request_repo
        self._ur_repo = user_roles_repo
        self._audit = audit_service
        self._session = session

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
        wf = self._repo.create_workflow(wf)
        self._session.commit()
        
        approval_required.send(
            self,
            payload={
                "event": "approval_required",
                "workflow_id": str(wf.id),
                "request_id": str(access_request_id),
                "recipient_id": str(approver_id),
                "title": "Approval Required",
                "message": f"You have a new access request pending your approval.",
                "type": "approval_required",
                "priority": "high",
            }
        )
        return wf

    def approve(self, workflow_id: UUID, approver_id: UUID, comments: str | None = None) -> ApprovalWorkflow:
        wf = self._repo.get_by_id(workflow_id, for_update=True)
        if not wf:
            raise ApprovalWorkflowValidationError("Approval workflow not found.")
        
        validate_state_transition(wf.status, ApprovalStatus.APPROVED)
        
        if wf.approver_id != approver_id:
            raise ApprovalWorkflowValidationError("Approver mismatch.")

        try:
            old_status = wf.status
            wf.status = ApprovalStatus.APPROVED
            wf.comments = comments
            wf.approved_at = datetime.now(timezone.utc)
            self._repo.update_workflow(wf)

            # Update Access Request and Assign Roles
            req = self._ar_repo.get_by_id(wf.access_request_id)
            if req:
                self._ar_repo.approve(req.id, approver_id) # repo handles flush inside
                if req.requested_role_id:
                    try:
                        self._ur_repo.assign_role_to_user(
                            user_id=req.requester_id,
                            role_id=req.requested_role_id,
                            assigned_by_user_id=approver_id
                        )
                    except UserRoleAlreadyExistsError:
                        pass
            
            # Audit log
            self._audit.log_event(
                actor_user_id=approver_id,
                action="approval.approved",
                resource_type="approval_workflows",
                resource_id=str(wf.id),
                approval_workflow_id=wf.id,
                request_id=wf.access_request_id,
                status=AuditStatus.SUCCESS,
                severity=AuditSeverity.INFO,
                details={
                    "old_status": old_status.value,
                    "new_status": wf.status.value,
                    "comment": comments
                }
            )
            self._session.commit()
            return wf
        except Exception as e:
            self._session.rollback()
            workflow_failed.send(
                self,
                payload={
                    "event": "workflow_failed",
                    "workflow_id": str(workflow_id),
                    "actor_id": str(approver_id),
                    "recipient_id": str(approver_id), # notify the approver that their action failed? Or admin?
                    "title": "Workflow Error",
                    "message": f"An error occurred while approving the workflow: {str(e)}",
                    "type": "system",
                    "priority": "high",
                }
            )
            raise e

    def reject(self, workflow_id: UUID, rejecter_id: UUID, comments: str | None = None) -> ApprovalWorkflow:
        wf = self._repo.get_by_id(workflow_id, for_update=True)
        if not wf:
            raise ApprovalWorkflowValidationError("Approval workflow not found.")
            
        validate_state_transition(wf.status, ApprovalStatus.REJECTED)
        
        if wf.approver_id != rejecter_id:
            raise ApprovalWorkflowValidationError("Approver mismatch.")

        try:
            old_status = wf.status
            wf.status = ApprovalStatus.REJECTED
            wf.comments = comments
            self._repo.update_workflow(wf)

            # Update Access Request
            req = self._ar_repo.get_by_id(wf.access_request_id)
            if req:
                self._ar_repo.reject(req.id, reason=comments or "Rejected by workflow", rejecter_id=rejecter_id)
            
            # Audit log
            self._audit.log_event(
                actor_user_id=rejecter_id,
                action="approval.rejected",
                resource_type="approval_workflows",
                resource_id=str(wf.id),
                approval_workflow_id=wf.id,
                request_id=wf.access_request_id,
                status=AuditStatus.SUCCESS,
                severity=AuditSeverity.INFO,
                details={
                    "old_status": old_status.value,
                    "new_status": wf.status.value,
                    "comment": comments
                }
            )
            self._session.commit()
            return wf
        except Exception as e:
            self._session.rollback()
            raise e

    def cancel(self, workflow_id: UUID, canceller_id: UUID, comments: str | None = None) -> ApprovalWorkflow:
        wf = self._repo.get_by_id(workflow_id, for_update=True)
        if not wf:
            raise ApprovalWorkflowValidationError("Approval workflow not found.")
            
        validate_state_transition(wf.status, ApprovalStatus.CANCELLED)

        try:
            old_status = wf.status
            wf.status = ApprovalStatus.CANCELLED
            wf.comments = comments
            self._repo.update_workflow(wf)
            
            # Audit log
            self._audit.log_event(
                actor_user_id=canceller_id,
                action="approval.cancelled",
                resource_type="approval_workflows",
                resource_id=str(wf.id),
                approval_workflow_id=wf.id,
                request_id=wf.access_request_id,
                status=AuditStatus.SUCCESS,
                severity="INFO",
                details={
                    "old_status": old_status.value,
                    "new_status": wf.status.value,
                    "comment": comments
                }
            )
            self._session.commit()
            return wf
        except Exception as e:
            self._session.rollback()
            raise e

    def cancel_workflow_for_request(self, access_request_id: UUID, comments: str | None = None) -> None:
        """Cancel pending approvals for a request."""
        workflows = self._repo.get_by_request(access_request_id)
        for wf in workflows:
            if wf.status == ApprovalStatus.PENDING:
                try:
                    wf = self._repo.get_by_id(wf.id, for_update=True)
                    if wf and wf.status == ApprovalStatus.PENDING:
                        wf.status = ApprovalStatus.CANCELLED
                        wf.comments = comments
                        self._repo.update_workflow(wf)
                        self._session.commit()
                except Exception:
                    self._session.rollback()

__all__ = ["ApprovalWorkflowService"]
