"""Repository for ApprovalWorkflow"""
from __future__ import annotations
from typing import Sequence, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.approval_workflow.exceptions import (
    ApprovalWorkflowNotFoundError,
    ApprovalWorkflowRepositoryError,
)
from app.approval_workflow.models import ApprovalWorkflow, ApprovalStatus

def _normalize_pagination(page: int | None, page_size: int | None) -> tuple[int, int]:
    """Normalize pagination parameters."""
    p = page if page is not None and page > 0 else 1
    s = page_size if page_size is not None and page_size > 0 else 50
    return p, min(s, 100)

class ApprovalWorkflowRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_workflow(self, workflow: ApprovalWorkflow) -> ApprovalWorkflow:
        try:
            self._session.add(workflow)
            self._session.commit()
            self._session.refresh(workflow)
            return workflow
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to create workflow.") from err

    def get_by_id(self, workflow_id: UUID) -> ApprovalWorkflow | None:
        try:
            stmt = select(ApprovalWorkflow).where(ApprovalWorkflow.id == workflow_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to get workflow.") from err

    def get_by_request(self, access_request_id: UUID) -> Sequence[ApprovalWorkflow]:
        try:
            stmt = select(ApprovalWorkflow).where(ApprovalWorkflow.access_request_id == access_request_id).order_by(ApprovalWorkflow.created_at.asc())
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to get workflows by request.") from err

    def list_pending(self) -> Sequence[ApprovalWorkflow]:
        try:
            stmt = select(ApprovalWorkflow).where(ApprovalWorkflow.status == ApprovalStatus.PENDING)
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to list pending workflows.") from err

    def approve(self, workflow_id: UUID, comments: str | None = None) -> ApprovalWorkflow:
        wf = self.get_by_id(workflow_id)
        if not wf:
            raise ApprovalWorkflowNotFoundError("Approval workflow not found.")
        try:
            wf.status = ApprovalStatus.APPROVED
            wf.comments = comments
            now = datetime.now(timezone.utc)
            wf.approved_at = now
            wf.updated_at = now
            self._session.commit()
            self._session.refresh(wf)
            return wf
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to approve workflow.") from err

    def reject(self, workflow_id: UUID, comments: str | None = None) -> ApprovalWorkflow:
        wf = self.get_by_id(workflow_id)
        if not wf:
            raise ApprovalWorkflowNotFoundError("Approval workflow not found.")
        try:
            wf.status = ApprovalStatus.REJECTED
            wf.comments = comments
            wf.updated_at = datetime.now(timezone.utc)
            self._session.commit()
            self._session.refresh(wf)
            return wf
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to reject workflow.") from err

    def cancel(self, workflow_id: UUID, comments: str | None = None) -> ApprovalWorkflow:
        wf = self.get_by_id(workflow_id)
        if not wf:
            raise ApprovalWorkflowNotFoundError("Approval workflow not found.")
        try:
            wf.status = ApprovalStatus.CANCELLED
            wf.comments = comments
            wf.updated_at = datetime.now(timezone.utc)
            self._session.commit()
            self._session.refresh(wf)
            return wf
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to cancel workflow.") from err

    def list(self, page: int = 1, page_size: int = 50) -> Sequence[ApprovalWorkflow]:
        p, s = _normalize_pagination(page, page_size)
        try:
            stmt = select(ApprovalWorkflow).order_by(ApprovalWorkflow.created_at.desc()).offset((p - 1) * s).limit(s)
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to list workflows.") from err

    def count(self) -> int:
        try:
            stmt = select(func.count(ApprovalWorkflow.id))
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to count workflows.") from err

__all__ = ["ApprovalWorkflowRepository"]
