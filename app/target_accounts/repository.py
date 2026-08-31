"""Repository for TargetAccountBinding domain entities."""

from __future__ import annotations

from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.target_accounts.models import (
    TargetAccountBinding,
    TargetAccountBindingStatus,
)


class TargetAccountBindingRepository:
    """SQLAlchemy repository for TargetAccountBinding entities."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(
        self,
        binding_id: UUID,
        for_update: bool = False,
    ) -> Optional[TargetAccountBinding]:
        """Fetch binding by primary key."""
        stmt = select(TargetAccountBinding).where(TargetAccountBinding.id == binding_id)
        if for_update:
            stmt = stmt.with_for_update()
        return self._session.execute(stmt).scalar_one_or_none()

    def find_by_user_and_resource(
        self,
        user_id: UUID,
        resource_id: UUID,
        for_update: bool = False,
    ) -> Optional[TargetAccountBinding]:
        """Fetch binding for a specific (user, resource) pair."""
        stmt = select(TargetAccountBinding).where(
            TargetAccountBinding.control_plane_user_id == user_id,
            TargetAccountBinding.resource_id == resource_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self._session.execute(stmt).scalar_one_or_none()

    def find_by_resource_and_os_username(
        self,
        resource_id: UUID,
        target_os_username: str,
    ) -> Optional[TargetAccountBinding]:
        """Fetch binding for a specific resource and target OS username."""
        stmt = select(TargetAccountBinding).where(
            TargetAccountBinding.resource_id == resource_id,
            TargetAccountBinding.target_os_username == target_os_username,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_user(
        self,
        user_id: UUID,
        status: Optional[TargetAccountBindingStatus] = None,
    ) -> Sequence[TargetAccountBinding]:
        """List all bindings for a given Control Plane user."""
        stmt = select(TargetAccountBinding).where(
            TargetAccountBinding.control_plane_user_id == user_id
        )
        if status is not None:
            stmt = stmt.where(TargetAccountBinding.status == status)
        return self._session.execute(stmt).scalars().all()

    def list_by_resource(
        self,
        resource_id: UUID,
    ) -> Sequence[TargetAccountBinding]:
        """List all bindings for a given Resource."""
        stmt = select(TargetAccountBinding).where(
            TargetAccountBinding.resource_id == resource_id
        )
        return self._session.execute(stmt).scalars().all()

    def get_existing_os_usernames(self, resource_id: UUID) -> List[str]:
        """Return all target OS usernames registered on a resource."""
        stmt = select(TargetAccountBinding.target_os_username).where(
            TargetAccountBinding.resource_id == resource_id
        )
        return list(self._session.execute(stmt).scalars().all())

    def create(self, binding: TargetAccountBinding) -> TargetAccountBinding:
        """Persist a new binding entity."""
        self._session.add(binding)
        self._session.flush()
        return binding

    def save(self, binding: TargetAccountBinding) -> TargetAccountBinding:
        """Update and flush an existing binding entity."""
        binding.row_version = (binding.row_version or 1) + 1
        self._session.add(binding)
        self._session.flush()
        return binding
