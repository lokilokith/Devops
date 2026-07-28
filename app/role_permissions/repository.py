"""RolePermissions repository for OpsForge.

This module provides database access logic
for RolePermission entities.
"""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.role_permissions.exceptions import (
    RolePermissionAlreadyExistsError,
    RolePermissionNotFoundError,
    RolePermissionsRepositoryError,
)
from app.role_permissions.models import RolePermission
from app.roles.models import Role
from app.permissions.models import Permission

class RolePermissionsRepository:
    """
    Repository managing persistence and retrieval
    operations for RolePermission association entities.
    """

    def __init__(self, session: Session) -> None:
        """Initialize repository with a SQLAlchemy session.

        Args:
            session: Active SQLAlchemy database session.
        """
        self._session = session

    def assign_permission_to_role(
        self, role_id: UUID, permission_id: UUID, assigned_by_user_id: UUID | None = None
    ) -> RolePermission:
        """Assign a permission to a role.

        Args:
            role_id: Unique role identifier.
            permission_id: Unique permission identifier.
            assigned_by_user_id: Optional user ID who assigned the permission.

        Returns:
            The created RolePermission instance.

        Raises:
            RolePermissionAlreadyExistsError: If association already exists.
            RolePermissionsRepositoryError: If the database operation fails.
        """
        if self.exists(role_id, permission_id):
            raise RolePermissionAlreadyExistsError("Permission is already assigned to the role.")
        try:
            rp = RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                assigned_by_user_id=assigned_by_user_id,
            )
            self._session.add(rp)
            self._session.commit()
            self._session.refresh(rp)
            return rp
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolePermissionsRepositoryError("Failed to assign permission to role.") from err

    def remove_permission_from_role(self, role_id: UUID, permission_id: UUID) -> bool:
        """Remove a permission from a role.

        Args:
            role_id: Unique role identifier.
            permission_id: Unique permission identifier.

        Returns:
            True if removed successfully.

        Raises:
            RolePermissionNotFoundError: If the association doesn't exist.
            RolePermissionsRepositoryError: If the database operation fails.
        """
        try:
            stmt = select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
            rp = self._session.execute(stmt).scalar_one_or_none()
            if not rp:
                raise RolePermissionNotFoundError("RolePermission association not found.")
            
            self._session.delete(rp)
            self._session.commit()
            return True
        except RolePermissionNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolePermissionsRepositoryError("Failed to remove permission from role.") from err

    def list_permissions_for_role(self, role_id: UUID) -> Sequence[Permission]:
        """List all permissions assigned to a given role.

        Args:
            role_id: Unique role identifier.

        Returns:
            Sequence of Permission instances.

        Raises:
            RolePermissionsRepositoryError: If the database query fails.
        """
        try:
            stmt = (
                select(Permission)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role_id)
                .order_by(RolePermission.assigned_at.desc())
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolePermissionsRepositoryError("Failed to list permissions for role.") from err

    def list_roles_for_permission(self, permission_id: UUID) -> Sequence[Role]:
        """List all roles that have a given permission.

        Args:
            permission_id: Unique permission identifier.

        Returns:
            Sequence of Role instances.

        Raises:
            RolePermissionsRepositoryError: If the database query fails.
        """
        try:
            stmt = (
                select(Role)
                .join(RolePermission, RolePermission.role_id == Role.id)
                .where(RolePermission.permission_id == permission_id)
                .order_by(RolePermission.assigned_at.desc())
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolePermissionsRepositoryError("Failed to list roles for permission.") from err

    def exists(self, role_id: UUID, permission_id: UUID) -> bool:
        """Check if a specific permission is assigned to a specific role.

        Args:
            role_id: Unique role identifier.
            permission_id: Unique permission identifier.

        Returns:
            True if assigned, False otherwise.

        Raises:
            RolePermissionsRepositoryError: If the database query fails.
        """
        try:
            stmt = select(exists().where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            ))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise RolePermissionsRepositoryError("Failed to check existence.") from err

__all__ = ["RolePermissionsRepository"]
