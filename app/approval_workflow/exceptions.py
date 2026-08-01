"""Exceptions for Approval Workflow"""


class ApprovalWorkflowError(Exception):
    """Base exception for all Approval Workflow module errors."""


class ApprovalWorkflowRepositoryError(ApprovalWorkflowError):
    """Raised when a repository operation fails."""


class ApprovalWorkflowNotFoundError(ApprovalWorkflowRepositoryError):
    """Raised when the requested approval workflow cannot be found."""


class ApprovalWorkflowInvalidStateError(ApprovalWorkflowError):
    """Raised when the workflow state transition is invalid."""


class ApprovalWorkflowValidationError(ApprovalWorkflowError):
    """Raised when business logic validation fails."""
