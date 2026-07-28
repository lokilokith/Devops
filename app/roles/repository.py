"""Roles repository for OpsForge.

This module provides database access logic
for Role entities within the PAM platform.
"""

from __future__ import annotations

from typing import Any, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import Select, exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.roles.exceptions import RoleNotFoundError, RolesRepositoryError
from app.roles.models import Role, RoleStatus, RoleType
from app.shared.database import BaseModel

T = TypeVar("T", bound=BaseModel)


class RolesRepository:
    """
    Repository managing persistence and retrieval
    operations for Role entities.
    """

    def __init__(self, session: Session) -> None:
        """Initialize repository with a SQLAlchemy session.

        Args:
            session: Active SQLAlchemy database session.
        """
        self._session = session

    def _get_role_or_raise(self, role_id: UUID) -> Role:
        """Fetch a Role entity by ID or raise RoleNotFoundError.

        Args:
            role_id: Unique role identifier.

        Returns:
            Role instance.

        Raises:
            RoleNotFoundError: If the role does not exist.
        """
        role = self.get_by_id(role_id)
        if not role:
            raise RoleNotFoundError(f"Role with ID '{role_id}' not found.")
        return role

    def _commit_and_refresh(self, entity: T) -> T:
        """Commit session changes and refresh the given ORM entity.

        Args:
            entity: Domain ORM entity to commit and refresh.

        Returns:
            Refreshed domain ORM entity instance.
        """
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def _commit_only(self) -> None:
        """
        Commit session changes without executing
        a post-commit entity refresh.
        """
        self._session.commit()

    @staticmethod
    def _normalize_pagination(limit: int, offset: int) -> tuple[int, int]:
        """
        Bound limit to a maximum threshold
        and ensure offset is non-negative.

        Args:
            limit: Requested max number of records.
            offset: Requested record offset.

        Returns:
            Tuple of (bounded_limit, normalized_offset).
        """
        bounded_limit = min(max(1, limit), 1000)
        normalized_offset = max(0, offset)
        return bounded_limit, normalized_offset

    def _apply_filters(
        self,
        stmt: Select[Any],
        *,
        role_code: str | None = None,
        role_name: str | None = None,
        status: RoleStatus | None = None,
        role_type: RoleType | None = None,
    ) -> Select[Any]:
        """Apply normalized search and classification filters to a query.

        Args:
            stmt: Select statement targeting the Role entity or aggregates.
            role_code: Partial or exact role code filter.
            role_name: Partial or exact role name filter.
            status: RoleStatus enum filter.
            role_type: RoleType enum filter.

        Returns:
            Filtered Select statement.
        """
        filters: list[Any] = []

        if role_code is not None and role_code.strip():
            filters.append(Role.role_code.ilike(f"%{role_code.strip()}%"))
        if role_name is not None and role_name.strip():
            filters.append(Role.role_name.ilike(f"%{role_name.strip()}%"))
        if status is not None:
            filters.append(Role.status == status)
        if role_type is not None:
            filters.append(Role.role_type == role_type)

        if filters:
            return stmt.where(*filters)
        return stmt

    def _update_status(self, role_id: UUID, new_status: RoleStatus) -> Role:
        """Internal helper to transition a Role to a new status state.

        Args:
            role_id: Unique role identifier.
            new_status: RoleStatus enum value.

        Returns:
            Updated Role instance.

        Raises:
            RoleNotFoundError: If the role does not exist.
            RolesRepositoryError: If the database operation fails.
        """
        try:
            role = self._get_role_or_raise(role_id)
            role.status = new_status
            return self._commit_and_refresh(role)
        except RoleNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                f"Failed to set role status to '{new_status.value}'."
            ) from err

    def create(self, role: Role) -> Role:
        """Persist a new Role entity.

        Args:
            role: Unpersisted Role instance.

        Returns:
            The created Role instance.

        Raises:
            RolesRepositoryError: If the database operation fails.
        """
        try:
            self._session.add(role)
            return self._commit_and_refresh(role)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                "Failed to create role database record."
            ) from err

    def get_by_id(self, role_id: UUID) -> Role | None:
        """Fetch a Role entity by primary key ID.

        Args:
            role_id: Unique role identifier.

        Returns:
            Role instance if found, None otherwise.

        Raises:
            RolesRepositoryError: If the database query fails.
        """
        try:
            stmt = select(Role).where(Role.id == role_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                "Failed to retrieve role by ID."
            ) from err

    def get_by_role_code(self, role_code: str) -> Role | None:
        """Fetch a Role entity by role code (exact match).

        Args:
            role_code: Unique technical role code.

        Returns:
            Role instance if found, None otherwise.

        Raises:
            RolesRepositoryError: If the database query fails.
        """
        try:
            normalized_code = role_code.strip()
            stmt = select(Role).where(Role.role_code == normalized_code)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                "Failed to retrieve role by role code."
            ) from err

    def get_by_role_name(self, role_name: str) -> Role | None:
        """Fetch a Role entity by role name (exact match).

        Args:
            role_name: Unique human-readable role name.

        Returns:
            Role instance if found, None otherwise.

        Raises:
            RolesRepositoryError: If the database query fails.
        """
        try:
            normalized_name = role_name.strip()
            stmt = select(Role).where(Role.role_name == normalized_name)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                "Failed to retrieve role by role name."
            ) from err

    def list(
        self,
        *,
        status: RoleStatus | None = None,
        role_type: RoleType | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Role]:
        """
        List roles with optional status/type filtering,
        pagination, and deterministic ordering.

        Args:
            status: Optional RoleStatus enum filter.
            role_type: Optional RoleType enum filter.
            offset: Number of records to skip (normalized to >= 0).
            limit: Maximum number of records to return (capped at 1000).

        Returns:
            Sequence of Role instances sorted by creation time descending.

        Raises:
            RolesRepositoryError: If the database query fails.
        """
        try:
            bounded_limit, normalized_offset = (
                self._normalize_pagination(limit, offset)
            )
            stmt = select(Role)
            stmt = self._apply_filters(
                stmt,
                status=status,
                role_type=role_type,
            )
            stmt = (
                stmt.order_by(Role.created_at.desc())
                .offset(normalized_offset)
                .limit(bounded_limit)
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError("Failed to list roles.") from err

    def update(self, role: Role) -> Role:
        """Persist state updates for a Role entity.

        Args:
            role: Role instance containing updated attributes.

        Returns:
            The persisted Role instance.

        Raises:
            RolesRepositoryError: If the database operation fails.
        """
        try:
            merged_role = self._session.merge(role)
            return self._commit_and_refresh(merged_role)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                "Failed to update role record."
            ) from err

    def delete(self, role_id: UUID) -> bool:
        """Delete a Role entity by ID.

        Args:
            role_id: Unique role identifier.

        Returns:
            True if deleted.

        Raises:
            RoleNotFoundError: If the role does not exist.
            RolesRepositoryError: If the database operation fails.
        """
        try:
            role = self._get_role_or_raise(role_id)
            self._session.delete(role)
            self._commit_only()
            return True
        except RoleNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                "Failed to delete role record."
            ) from err

    def activate(self, role_id: UUID) -> Role:
        """Activate a Role entity.

        Args:
            role_id: Unique role identifier.

        Returns:
            Updated Role instance.

        Raises:
            RoleNotFoundError: If the role does not exist.
            RolesRepositoryError: If the database operation fails.
        """
        return self._update_status(role_id, RoleStatus.ACTIVE)

    def deactivate(self, role_id: UUID) -> Role:
        """Deactivate a Role entity.

        Args:
            role_id: Unique role identifier.

        Returns:
            Updated Role instance.

        Raises:
            RoleNotFoundError: If the role does not exist.
            RolesRepositoryError: If the database operation fails.
        """
        return self._update_status(role_id, RoleStatus.INACTIVE)

    def retire(self, role_id: UUID) -> Role:
        """Retire a Role entity.

        Args:
            role_id: Unique role identifier.

        Returns:
            Updated Role instance.

        Raises:
            RoleNotFoundError: If the role does not exist.
            RolesRepositoryError: If the database operation fails.
        """
        return self._update_status(role_id, RoleStatus.RETIRED)

    def exists_by_role_code(self, role_code: str) -> bool:
        """Check if a role exists with the given role code.

        Args:
            role_code: Role code to check.

        Returns:
            True if exists, False otherwise.

        Raises:
            RolesRepositoryError: If the database query fails.
        """
        try:
            normalized_code = role_code.strip()
            stmt = select(exists().where(Role.role_code == normalized_code))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                "Failed to check role code existence."
            ) from err

    def exists_by_role_name(self, role_name: str) -> bool:
        """Check if a role exists with the given role name.

        Args:
            role_name: Role name to check.

        Returns:
            True if exists, False otherwise.

        Raises:
            RolesRepositoryError: If the database query fails.
        """
        try:
            normalized_name = role_name.strip()
            stmt = select(exists().where(Role.role_name == normalized_name))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError(
                "Failed to check role name existence."
            ) from err

    def count(
        self,
        *,
        status: RoleStatus | None = None,
        role_type: RoleType | None = None,
    ) -> int:
        """Count total Role records matching optional filters.

        Args:
            status: Optional RoleStatus enum filter.
            role_type: Optional RoleType enum filter.

        Returns:
            Total number of matching Role instances.

        Raises:
            RolesRepositoryError: If the database query fails.
        """
        try:
            stmt = select(func.count(Role.id))
            stmt = self._apply_filters(
                stmt,
                status=status,
                role_type=role_type,
            )
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError("Failed to count roles.") from err

    def search(
        self,
        *,
        role_code: str | None = None,
        role_name: str | None = None,
        status: RoleStatus | None = None,
        role_type: RoleType | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Role]:
        """
        Search roles matching optional filters
        sorted by created_at descending.

        Args:
            role_code:
                Partial or exact role code to filter by
                (case-insensitive substring).
            role_name:
                Partial or exact role name to filter by
                (case-insensitive substring).
            status: RoleStatus enum filter.
            role_type: RoleType enum filter.
            offset: Number of records to skip (normalized to >= 0).
            limit: Maximum number of records to return (capped at 1000).

        Returns:
            Sequence of matching Role instances.

        Raises:
            RolesRepositoryError: If the database query fails.
        """
        try:
            bounded_limit, normalized_offset = (
                self._normalize_pagination(limit, offset)
            )
            stmt = select(Role)
            stmt = self._apply_filters(
                stmt,
                role_code=role_code,
                role_name=role_name,
                status=status,
                role_type=role_type,
            )
            stmt = (
                stmt.order_by(Role.created_at.desc())
                .offset(normalized_offset)
                .limit(bounded_limit)
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolesRepositoryError("Failed to search roles.") from err


__all__ = [
    "RolesRepository",
]
