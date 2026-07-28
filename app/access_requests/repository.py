"""AccessRequest repository for OpsForge."""
from __future__ import annotations
from typing import Sequence, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.access_requests.exceptions import (
    AccessRequestNotFoundError,
    AccessRequestRepositoryError,
)
from app.access_requests.models import AccessRequest, AccessRequestStatus

def _normalize_pagination(page: int | None, page_size: int | None) -> tuple[int, int]:
    """Normalize pagination parameters."""
    p = page if page is not None and page > 0 else 1
    s = page_size if page_size is not None and page_size > 0 else 50
    return p, min(s, 100)

class AccessRequestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_request(self, access_request: AccessRequest) -> AccessRequest:
        try:
            self._session.add(access_request)
            self._session.commit()
            self._session.refresh(access_request)
            return access_request
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to create access request.") from err

    def get_by_id(self, request_id: UUID) -> AccessRequest | None:
        try:
            stmt = select(AccessRequest).where(AccessRequest.id == request_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to get access request.") from err

    def get_by_request_number(self, request_number: str) -> AccessRequest | None:
        try:
            stmt = select(AccessRequest).where(AccessRequest.request_number == request_number)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to get access request by number.") from err

    def update_status(self, request_id: UUID, status: AccessRequestStatus) -> AccessRequest:
        req = self.get_by_id(request_id)
        if not req:
            raise AccessRequestNotFoundError("Access request not found.")
        try:
            req.status = status
            req.updated_at = datetime.now(timezone.utc)
            self._session.commit()
            self._session.refresh(req)
            return req
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to update status.") from err

    def approve(self, request_id: UUID, approver_id: UUID) -> AccessRequest:
        req = self.get_by_id(request_id)
        if not req:
            raise AccessRequestNotFoundError("Access request not found.")
        try:
            req.status = AccessRequestStatus.APPROVED
            req.approved_by = approver_id
            now = datetime.now(timezone.utc)
            req.approved_at = now
            req.updated_at = now
            self._session.commit()
            self._session.refresh(req)
            return req
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to approve request.") from err

    def reject(self, request_id: UUID, reason: str, rejecter_id: UUID | None = None) -> AccessRequest:
        req = self.get_by_id(request_id)
        if not req:
            raise AccessRequestNotFoundError("Access request not found.")
        try:
            req.status = AccessRequestStatus.REJECTED
            req.rejected_reason = reason
            req.updated_at = datetime.now(timezone.utc)
            self._session.commit()
            self._session.refresh(req)
            return req
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to reject request.") from err

    def cancel(self, request_id: UUID) -> AccessRequest:
        return self.update_status(request_id, AccessRequestStatus.CANCELLED)

    def list_requests(self, page: int = 1, page_size: int = 50) -> Sequence[AccessRequest]:
        p, s = _normalize_pagination(page, page_size)
        try:
            stmt = select(AccessRequest).order_by(AccessRequest.created_at.desc()).offset((p - 1) * s).limit(s)
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to list requests.") from err

    def count(self, **filters: Any) -> int:
        try:
            stmt = select(func.count(AccessRequest.id))
            stmt = self._apply_filters(stmt, **filters)
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to count requests.") from err

    def search(self, page: int = 1, page_size: int = 50, **filters: Any) -> Sequence[AccessRequest]:
        p, s = _normalize_pagination(page, page_size)
        try:
            stmt = select(AccessRequest)
            stmt = self._apply_filters(stmt, **filters)
            stmt = stmt.order_by(AccessRequest.created_at.desc()).offset((p - 1) * s).limit(s)
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AccessRequestRepositoryError("Failed to search requests.") from err

    def _apply_filters(self, stmt: Any, **filters: Any) -> Any:
        if "status" in filters and filters["status"]:
            stmt = stmt.where(AccessRequest.status == filters["status"])
        if "requester_id" in filters and filters["requester_id"]:
            stmt = stmt.where(AccessRequest.requester_id == filters["requester_id"])
        if "requested_role_id" in filters and filters["requested_role_id"]:
            stmt = stmt.where(AccessRequest.requested_role_id == filters["requested_role_id"])
        if "requested_resource_id" in filters and filters["requested_resource_id"]:
            stmt = stmt.where(AccessRequest.requested_resource_id == filters["requested_resource_id"])
        return stmt

__all__ = ["AccessRequestRepository"]
