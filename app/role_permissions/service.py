"""RolePermissions feature service layer."""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app.role_permissions.repository import RolePermissionsRepository
from app.role_permissions.models import RolePermission
from app.roles.models import Role
from app.permissions.models import Permission
from app.roles.repository import RolesRepository
from app.permissions.repository import PermissionsRepository
from app.role_permissions.exceptions import (
    RolePermissionsRepositoryError,
    RolePermissionNotFoundError,
    RolePermissionAlreadyExistsError,
    RolePermissionsServiceError,
    ValidationError
)

class RolePermissionService:
    def __init__(
        self, 
        repository: RolePermissionsRepository,
        roles_repository: RolesRepository,
        permissions_repository: PermissionsRepository
    ):
        self._repository = repository
        self._roles_repository = roles_repository
        self._permissions_repository = permissions_repository
        
    def assign_permission(self, role_id: UUID, permission_id: UUID, assigned_by_user_id: UUID | None = None) -> RolePermission:
        try:
            role = self._roles_repository.get_by_id(role_id)
            if not role:
                raise ValidationError("Role does not exist.")
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise RolePermissionsServiceError("Error checking role.") from e

        try:
            permission = self._permissions_repository.get_by_id(permission_id)
            if not permission:
                raise ValidationError("Permission does not exist.")
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise RolePermissionsServiceError("Error checking permission.") from e

        try:
            return self._repository.assign_permission_to_role(role_id, permission_id, assigned_by_user_id)
        except RolePermissionAlreadyExistsError as e:
            raise ValidationError(str(e)) from e
        except RolePermissionsRepositoryError as e:
            raise RolePermissionsServiceError(f"Failed to assign permission: {e}") from e

    def remove_permission(self, role_id: UUID, permission_id: UUID) -> bool:
        try:
            return self._repository.remove_permission_from_role(role_id, permission_id)
        except RolePermissionNotFoundError as e:
            raise ValidationError(str(e)) from e
        except RolePermissionsRepositoryError as e:
            raise RolePermissionsServiceError(f"Failed to remove permission: {e}") from e

    def list_permissions_for_role(self, role_id: UUID) -> Sequence[Permission]:
        try:
            return self._repository.list_permissions_for_role(role_id)
        except RolePermissionsRepositoryError as e:
            raise RolePermissionsServiceError(f"Failed to list permissions for role: {e}") from e

    def list_roles_for_permission(self, permission_id: UUID) -> Sequence[Role]:
        try:
            return self._repository.list_roles_for_permission(permission_id)
        except RolePermissionsRepositoryError as e:
            raise RolePermissionsServiceError(f"Failed to list roles for permission: {e}") from e

    def exists(self, role_id: UUID, permission_id: UUID) -> bool:
        try:
            return self._repository.exists(role_id, permission_id)
        except RolePermissionsRepositoryError as e:
            raise RolePermissionsServiceError(f"Failed to check existence: {e}") from e

    def count_permissions_for_role(self, role_id: UUID) -> int:
        return len(self.list_permissions_for_role(role_id))

    def count_roles_for_permission(self, permission_id: UUID) -> int:
        return len(self.list_roles_for_permission(permission_id))
