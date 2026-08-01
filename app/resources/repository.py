"""Resources repository for OpsForge.

This module provides database access logic
for Resource entities.
"""

from __future__ import annotations

from typing import Any, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import Select, exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.resources.exceptions import ResourceNotFoundError, ResourcesRepositoryError
from app.resources.models import Resource, ResourceStatus, ResourceType
from app.shared.database import BaseModel

T = TypeVar("T", bound=BaseModel)


class ResourcesRepository:
    """
    Repository managing persistence and retrieval
    operations for Resource entities.
    """

    def __init__(self, session: Session) -> None:
        """Initialize repository with a SQLAlchemy session.

        Args:
            session: Active SQLAlchemy database session.
        """
        self._session = session

    def _get_resource_or_raise(self, resource_id: UUID) -> Resource:
        """Fetch a Resource entity by ID or raise ResourceNotFoundError."""
        resource = self.get_by_id(resource_id)
        if not resource:
            raise ResourceNotFoundError(f"Resource with ID '{resource_id}' not found.")
        return resource

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
        resource_code: str | None = None,
        resource_name: str | None = None,
        status: ResourceStatus | None = None,
        resource_type: ResourceType | None = None,
    ) -> Select[Any]:
        """Apply normalized search and classification filters to a query."""
        filters: list[Any] = []

        if resource_code is not None and resource_code.strip():
            filters.append(Resource.resource_code.ilike(f"%{resource_code.strip()}%"))
        if resource_name is not None and resource_name.strip():
            filters.append(Resource.resource_name.ilike(f"%{resource_name.strip()}%"))
        if status is not None:
            filters.append(Resource.status == status)
        if resource_type is not None:
            filters.append(Resource.resource_type == resource_type)

        if filters:
            return stmt.where(*filters)
        return stmt

    def _update_status(self, resource_id: UUID, new_status: ResourceStatus) -> Resource:
        """Internal helper to transition a Resource to a new status state."""
        try:
            resource = self._get_resource_or_raise(resource_id)
            resource.status = new_status
            return self._commit_and_refresh(resource)
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError(
                f"Failed to set resource status to '{new_status.value}'."
            ) from err

    def create(self, resource: Resource) -> Resource:
        """Persist a new Resource entity."""
        try:
            self._session.add(resource)
            return self._commit_and_refresh(resource)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError(
                "Failed to create resource database record."
            ) from err

    def get_by_id(self, resource_id: UUID) -> Resource | None:
        """Fetch a Resource entity by primary key ID."""
        try:
            stmt = select(Resource).where(Resource.id == resource_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError(
                "Failed to retrieve resource by ID."
            ) from err

    def get_by_resource_code(self, resource_code: str) -> Resource | None:
        """Fetch a Resource entity by resource code (exact match)."""
        try:
            normalized_code = resource_code.strip()
            stmt = select(Resource).where(Resource.resource_code == normalized_code)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError(
                "Failed to retrieve resource by resource code."
            ) from err

    def get_by_resource_name(self, resource_name: str) -> Resource | None:
        """Fetch a Resource entity by resource name (exact match)."""
        try:
            normalized_name = resource_name.strip()
            stmt = select(Resource).where(Resource.resource_name == normalized_name)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError(
                "Failed to retrieve resource by resource name."
            ) from err

    def list(
        self,
        *,
        status: ResourceStatus | None = None,
        resource_type: ResourceType | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Resource]:
        """List resources with optional status/type filtering, pagination, and deterministic ordering."""
        try:
            bounded_limit, normalized_offset = self._normalize_pagination(limit, offset)
            stmt = select(Resource)
            stmt = self._apply_filters(
                stmt,
                status=status,
                resource_type=resource_type,
            )
            stmt = (
                stmt.order_by(Resource.created_at.desc())
                .offset(normalized_offset)
                .limit(bounded_limit)
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError("Failed to list resources.") from err

    def update(self, resource: Resource) -> Resource:
        """Persist state updates for a Resource entity."""
        try:
            merged_resource = self._session.merge(resource)
            return self._commit_and_refresh(merged_resource)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError("Failed to update resource record.") from err

    def delete(self, resource_id: UUID) -> bool:
        """Delete a Resource entity by ID."""
        try:
            resource = self._get_resource_or_raise(resource_id)
            self._session.delete(resource)
            self._commit_only()
            return True
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError("Failed to delete resource record.") from err

    def activate(self, resource_id: UUID) -> Resource:
        """Activate a Resource entity."""
        return self._update_status(resource_id, ResourceStatus.ACTIVE)

    def deactivate(self, resource_id: UUID) -> Resource:
        """Deactivate a Resource entity."""
        return self._update_status(resource_id, ResourceStatus.INACTIVE)

    def retire(self, resource_id: UUID) -> Resource:
        """Retire a Resource entity."""
        return self._update_status(resource_id, ResourceStatus.RETIRED)

    def exists_by_resource_code(self, resource_code: str) -> bool:
        """Check if a resource exists with the given resource code."""
        try:
            normalized_code = resource_code.strip()
            stmt = select(exists().where(Resource.resource_code == normalized_code))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError(
                "Failed to check resource code existence."
            ) from err

    def exists_by_resource_name(self, resource_name: str) -> bool:
        """Check if a resource exists with the given resource name."""
        try:
            normalized_name = resource_name.strip()
            stmt = select(exists().where(Resource.resource_name == normalized_name))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError(
                "Failed to check resource name existence."
            ) from err

    def count(
        self,
        *,
        status: ResourceStatus | None = None,
        resource_type: ResourceType | None = None,
    ) -> int:
        """Count total Resource records matching optional filters."""
        try:
            stmt = select(func.count(Resource.id))
            stmt = self._apply_filters(
                stmt,
                status=status,
                resource_type=resource_type,
            )
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError("Failed to count resources.") from err

    def search(
        self,
        *,
        resource_code: str | None = None,
        resource_name: str | None = None,
        status: ResourceStatus | None = None,
        resource_type: ResourceType | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Resource]:
        """Search resources matching optional filters sorted by created_at descending."""
        try:
            bounded_limit, normalized_offset = self._normalize_pagination(limit, offset)
            stmt = select(Resource)
            stmt = self._apply_filters(
                stmt,
                resource_code=resource_code,
                resource_name=resource_name,
                status=status,
                resource_type=resource_type,
            )
            stmt = (
                stmt.order_by(Resource.created_at.desc())
                .offset(normalized_offset)
                .limit(bounded_limit)
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise ResourcesRepositoryError("Failed to search resources.") from err


__all__ = [
    "ResourcesRepository",
]
