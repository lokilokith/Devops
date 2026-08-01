"""Authorization Engine Service."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.authorization.exceptions import (
    AuthorizationDeniedError,
    AuthorizationRepositoryError,
)
from app.identity.models import User
from app.permissions.models import Permission, PermissionAction
from app.resources.models import Resource
from app.role_permissions.models import RolePermission
from app.roles.models import Role, UserRole


class AuthorizationService:
    """Service for determining if a user is authorized to perform actions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def has_permission(
        self, user_id: UUID, resource_code: str, action: PermissionAction
    ) -> bool:
        """Check if user has permission to perform action on resource."""
        perm_code = f"PERM_{resource_code.upper()}_{action.value.upper()}"
        try:
            stmt = (
                select(Permission.id)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == user_id,
                    Permission.permission_code == perm_code,
                    Permission.action == action,
                )
            )
            return self._session.execute(stmt).first() is not None
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuthorizationRepositoryError("Failed to check permission.") from err

    def authorize(
        self, user_id: UUID, resource_code: str, action: PermissionAction
    ) -> None:
        """Authorize an action, raising if denied."""
        if not self.has_permission(user_id, resource_code, action):
            raise AuthorizationDeniedError(
                f"User is not authorized to {action.value} {resource_code}."
            )

    def get_user_permissions(self, user_id: UUID) -> Sequence[Permission]:
        """Get all permissions for a user."""
        try:
            stmt = (
                select(Permission)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(UserRole.user_id == user_id)
                .distinct()
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuthorizationRepositoryError(
                "Failed to get user permissions."
            ) from err

    def get_user_roles(self, user_id: UUID) -> Sequence[Role]:
        """Get all roles for a user."""
        try:
            stmt = (
                select(Role)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
                .distinct()
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuthorizationRepositoryError("Failed to get user roles.") from err

    def get_accessible_resources(self, user_id: UUID) -> Sequence[Resource]:
        """Get all resources a user can access."""
        try:
            from sqlalchemy import func

            stmt = (
                select(Resource)
                .join(
                    Permission,
                    Permission.permission_code.like(
                        "PERM_" + func.upper(Resource.resource_code) + "_%"
                    ),
                )
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(UserRole.user_id == user_id)
                .distinct()
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise AuthorizationRepositoryError(
                "Failed to get accessible resources."
            ) from err


__all__ = ["AuthorizationService"]
