"""Permissions repository for OpsForge.

This module provides database access logic
for Permission entities.
"""

from __future__ import annotations

from typing import Any, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import Select, exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.permissions.exceptions import PermissionNotFoundError, PermissionsRepositoryError
from app.permissions.models import Permission, PermissionStatus, PermissionAction
from app.shared.database import BaseModel

T = TypeVar("T", bound=BaseModel)

class PermissionsRepository:
    """
    Repository managing persistence and retrieval
    operations for Permission entities.
    """

    def __init__(self, session: Session) -> None:
        """Initialize repository with a SQLAlchemy session.

        Args:
            session: Active SQLAlchemy database session.
        """
        self._session = session

    def _get_permission_or_raise(self, permission_id: UUID) -> Permission:
        """Fetch a Permission entity by ID or raise PermissionNotFoundError."""
        permission = self.get_by_id(permission_id)
        if not permission:
            raise PermissionNotFoundError(f"Permission with ID '{permission_id}' not found.")
        return permission

    def _commit_and_refresh(self, entity: T) -> T:
        """Commit session changes and refresh the given ORM entity."""
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def _commit_only(self) -> None:
        """Commit session changes without executing a post-commit entity refresh."""
        self._session.commit()

    @staticmethod
    def _normalize_pagination(limit: int, offset: int) -> tuple[int, int]:
        """Bound limit to a maximum threshold and ensure offset is non-negative."""
        bounded_limit = min(max(1, limit), 1000)
        normalized_offset = max(0, offset)
        return bounded_limit, normalized_offset

    def _apply_filters(
        self,
        stmt: Select[Any],
        *,
        permission_code: str | None = None,
        permission_name: str | None = None,
        status: PermissionStatus | None = None,
        action: PermissionAction | None = None,
    ) -> Select[Any]:
        """Apply normalized search and classification filters to a query."""
        filters: list[Any] = []

        if permission_code is not None and permission_code.strip():
            filters.append(Permission.permission_code.ilike(f"%{permission_code.strip()}%"))
        if permission_name is not None and permission_name.strip():
            filters.append(Permission.permission_name.ilike(f"%{permission_name.strip()}%"))
        if status is not None:
            filters.append(Permission.status == status)
        if action is not None:
            filters.append(Permission.action == action)

        if filters:
            return stmt.where(*filters)
        return stmt

    def _update_status(self, permission_id: UUID, new_status: PermissionStatus) -> Permission:
        """Internal helper to transition a Permission to a new status state."""
        try:
            permission = self._get_permission_or_raise(permission_id)
            permission.status = new_status
            return self._commit_and_refresh(permission)
        except PermissionNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                f"Failed to set permission status to '{new_status.value}'."
            ) from err

    def create(self, permission: Permission) -> Permission:
        """Persist a new Permission entity."""
        try:
            self._session.add(permission)
            return self._commit_and_refresh(permission)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                "Failed to create permission database record."
            ) from err

    def get_by_id(self, permission_id: UUID) -> Permission | None:
        """Fetch a Permission entity by primary key ID."""
        try:
            stmt = select(Permission).where(Permission.id == permission_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                "Failed to retrieve permission by ID."
            ) from err

    def get_by_permission_code(self, permission_code: str) -> Permission | None:
        """Fetch a Permission entity by permission code (exact match)."""
        try:
            normalized_code = permission_code.strip()
            stmt = select(Permission).where(Permission.permission_code == normalized_code)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                "Failed to retrieve permission by permission code."
            ) from err

    def get_by_permission_name(self, permission_name: str) -> Permission | None:
        """Fetch a Permission entity by permission name (exact match)."""
        try:
            normalized_name = permission_name.strip()
            stmt = select(Permission).where(Permission.permission_name == normalized_name)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                "Failed to retrieve permission by permission name."
            ) from err

    def list(
        self,
        *,
        status: PermissionStatus | None = None,
        action: PermissionAction | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Permission]:
        """List permissions with optional status/action filtering, pagination, and deterministic ordering."""
        try:
            bounded_limit, normalized_offset = (
                self._normalize_pagination(limit, offset)
            )
            stmt = select(Permission)
            stmt = self._apply_filters(
                stmt,
                status=status,
                action=action,
            )
            stmt = (
                stmt.order_by(Permission.created_at.desc())
                .offset(normalized_offset)
                .limit(bounded_limit)
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError("Failed to list permissions.") from err

    def update(self, permission: Permission) -> Permission:
        """Persist state updates for a Permission entity."""
        try:
            merged_permission = self._session.merge(permission)
            return self._commit_and_refresh(merged_permission)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                "Failed to update permission record."
            ) from err

    def delete(self, permission_id: UUID) -> bool:
        """Delete a Permission entity by ID."""
        try:
            permission = self._get_permission_or_raise(permission_id)
            self._session.delete(permission)
            self._commit_only()
            return True
        except PermissionNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                "Failed to delete permission record."
            ) from err

    def activate(self, permission_id: UUID) -> Permission:
        """Activate a Permission entity."""
        return self._update_status(permission_id, PermissionStatus.ACTIVE)

    def deactivate(self, permission_id: UUID) -> Permission:
        """Deactivate a Permission entity."""
        return self._update_status(permission_id, PermissionStatus.INACTIVE)

    def retire(self, permission_id: UUID) -> Permission:
        """Retire a Permission entity."""
        return self._update_status(permission_id, PermissionStatus.RETIRED)

    def exists_by_permission_code(self, permission_code: str) -> bool:
        """Check if a permission exists with the given permission code."""
        try:
            normalized_code = permission_code.strip()
            stmt = select(exists().where(Permission.permission_code == normalized_code))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                "Failed to check permission code existence."
            ) from err

    def exists_by_permission_name(self, permission_name: str) -> bool:
        """Check if a permission exists with the given permission name."""
        try:
            normalized_name = permission_name.strip()
            stmt = select(exists().where(Permission.permission_name == normalized_name))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError(
                "Failed to check permission name existence."
            ) from err

    def count(
        self,
        *,
        status: PermissionStatus | None = None,
        action: PermissionAction | None = None,
    ) -> int:
        """Count total Permission records matching optional filters."""
        try:
            stmt = select(func.count(Permission.id))
            stmt = self._apply_filters(
                stmt,
                status=status,
                action=action,
            )
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError("Failed to count permissions.") from err

    def search(
        self,
        *,
        permission_code: str | None = None,
        permission_name: str | None = None,
        status: PermissionStatus | None = None,
        action: PermissionAction | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Permission]:
        """Search permissions matching optional filters sorted by created_at descending."""
        try:
            bounded_limit, normalized_offset = (
                self._normalize_pagination(limit, offset)
            )
            stmt = select(Permission)
            stmt = self._apply_filters(
                stmt,
                permission_code=permission_code,
                permission_name=permission_name,
                status=status,
                action=action,
            )
            stmt = (
                stmt.order_by(Permission.created_at.desc())
                .offset(normalized_offset)
                .limit(bounded_limit)
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PermissionsRepositoryError("Failed to search permissions.") from err

__all__ = [
    "PermissionsRepository",
]
