"""Audit repository for OpsForge."""
from __future__ import annotations
from typing import Sequence, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.audit.exceptions import (
    AuditRepositoryError,
)
from app.audit.models import AuditLog

def _normalize_pagination(page: int | None, page_size: int | None) -> tuple[int, int]:
    """Normalize pagination parameters."""
    p = page if page is not None and page > 0 else 1
    s = page_size if page_size is not None and page_size > 0 else 50
    return p, min(s, 100)

class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_log(self, audit_log: AuditLog) -> AuditLog:
        try:
            self._session.add(audit_log)
            self._session.commit()
            self._session.refresh(audit_log)
            return audit_log
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuditRepositoryError("Failed to create audit log.") from err

    def get_by_id(self, log_id: UUID) -> AuditLog | None:
        try:
            stmt = select(AuditLog).where(AuditLog.id == log_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuditRepositoryError("Failed to get audit log by ID.") from err

    def get_by_event_id(self, event_id: str) -> AuditLog | None:
        try:
            stmt = select(AuditLog).where(AuditLog.event_id == event_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuditRepositoryError("Failed to get audit log by event ID.") from err

    def list_logs(self, page: int = 1, page_size: int = 50) -> Sequence[AuditLog]:
        p, s = _normalize_pagination(page, page_size)
        try:
            stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).offset((p - 1) * s).limit(s)
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuditRepositoryError("Failed to list logs.") from err

    def search(self, page: int = 1, page_size: int = 50, **filters: Any) -> Sequence[AuditLog]:
        p, s = _normalize_pagination(page, page_size)
        try:
            stmt = select(AuditLog)
            stmt = self._apply_filters(stmt, **filters)
            stmt = stmt.order_by(AuditLog.timestamp.desc()).offset((p - 1) * s).limit(s)
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuditRepositoryError("Failed to search logs.") from err

    def count(self, **filters: Any) -> int:
        try:
            stmt = select(func.count(AuditLog.id))
            stmt = self._apply_filters(stmt, **filters)
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuditRepositoryError("Failed to count logs.") from err

    def filter_by_user(self, user_id: UUID, page: int = 1, page_size: int = 50) -> Sequence[AuditLog]:
        return self.search(page=page, page_size=page_size, actor_user_id=user_id)

    def filter_by_action(self, action: str, page: int = 1, page_size: int = 50) -> Sequence[AuditLog]:
        return self.search(page=page, page_size=page_size, action=action)

    def filter_by_date_range(self, start_date: datetime, end_date: datetime, page: int = 1, page_size: int = 50) -> Sequence[AuditLog]:
        return self.search(page=page, page_size=page_size, start_date=start_date, end_date=end_date)

    def _apply_filters(self, stmt: Any, **filters: Any) -> Any:
        if "status" in filters and filters["status"]:
            stmt = stmt.where(AuditLog.status == filters["status"])
        if "actor_user_id" in filters and filters["actor_user_id"]:
            stmt = stmt.where(AuditLog.actor_user_id == filters["actor_user_id"])
        if "action" in filters and filters["action"]:
            stmt = stmt.where(AuditLog.action == filters["action"])
        if "severity" in filters and filters["severity"]:
            stmt = stmt.where(AuditLog.severity == filters["severity"])
        if "start_date" in filters and filters["start_date"]:
            stmt = stmt.where(AuditLog.timestamp >= filters["start_date"])
        if "end_date" in filters and filters["end_date"]:
            stmt = stmt.where(AuditLog.timestamp <= filters["end_date"])
        return stmt

__all__ = ["AuditRepository"]
