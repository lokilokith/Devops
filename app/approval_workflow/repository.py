"""Repository for ApprovalWorkflow"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.approval_workflow.exceptions import ApprovalWorkflowRepositoryError
from app.approval_workflow.models import ApprovalStatus, ApprovalWorkflow


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
            self._session.flush()
            return workflow
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to create workflow.") from err

    def get_by_id(
        self, workflow_id: UUID, for_update: bool = False
    ) -> ApprovalWorkflow | None:
        try:
            stmt = select(ApprovalWorkflow).where(ApprovalWorkflow.id == workflow_id)
            if for_update:
                stmt = stmt.with_for_update()
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to get workflow.") from err

    def get_by_request(self, access_request_id: UUID) -> Sequence[ApprovalWorkflow]:
        try:
            stmt = (
                select(ApprovalWorkflow)
                .where(ApprovalWorkflow.access_request_id == access_request_id)
                .order_by(ApprovalWorkflow.created_at.asc())
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError(
                "Failed to get workflows by request."
            ) from err

    def update_workflow(self, workflow: ApprovalWorkflow) -> ApprovalWorkflow:
        try:
            workflow.updated_at = datetime.now(timezone.utc)
            self._session.flush()
            return workflow
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to update workflow.") from err

    def list(
        self,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        request_id: UUID | None = None,
        approver_id: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> Sequence[ApprovalWorkflow]:
        p, s = _normalize_pagination(page, page_size)
        try:
            stmt = select(ApprovalWorkflow)
            if status:
                stmt = stmt.where(ApprovalWorkflow.status == ApprovalStatus(status))
            if request_id:
                stmt = stmt.where(ApprovalWorkflow.access_request_id == request_id)
            if approver_id:
                stmt = stmt.where(ApprovalWorkflow.approver_id == approver_id)
            if created_after:
                stmt = stmt.where(ApprovalWorkflow.created_at >= created_after)
            if created_before:
                stmt = stmt.where(ApprovalWorkflow.created_at <= created_before)

            stmt = (
                stmt.order_by(ApprovalWorkflow.created_at.desc())
                .offset((p - 1) * s)
                .limit(s)
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to list workflows.") from err

    def count(
        self,
        status: str | None = None,
        request_id: UUID | None = None,
        approver_id: UUID | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        try:
            stmt = select(func.count(ApprovalWorkflow.id))
            if status:
                stmt = stmt.where(ApprovalWorkflow.status == ApprovalStatus(status))
            if request_id:
                stmt = stmt.where(ApprovalWorkflow.access_request_id == request_id)
            if approver_id:
                stmt = stmt.where(ApprovalWorkflow.approver_id == approver_id)
            if created_after:
                stmt = stmt.where(ApprovalWorkflow.created_at >= created_after)
            if created_before:
                stmt = stmt.where(ApprovalWorkflow.created_at <= created_before)
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ApprovalWorkflowRepositoryError("Failed to count workflows.") from err


__all__ = ["ApprovalWorkflowRepository"]
