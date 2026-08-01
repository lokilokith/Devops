"""Approval Workflow Validators"""

from __future__ import annotations

from app.approval_workflow.models import ApprovalStatus
from app.approval_workflow.exceptions import ApprovalWorkflowInvalidStateError

ALLOWED_TRANSITIONS = {
    ApprovalStatus.PENDING: {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.CANCELLED,
        # ApprovalStatus.EXPIRED, # Optional future addition
    },
    ApprovalStatus.APPROVED: set(),
    ApprovalStatus.REJECTED: set(),
    ApprovalStatus.CANCELLED: set(),
}


def validate_state_transition(
    current_status: ApprovalStatus, new_status: ApprovalStatus
) -> None:
    """Validate if a state transition is allowed."""
    if new_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise ApprovalWorkflowInvalidStateError(
            f"Invalid transition from {current_status.value} to {new_status.value}."
        )
