"""Permissions feature service layer."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app.permissions.repository import PermissionsRepository
from app.permissions.models import Permission, PermissionAction, PermissionStatus
from app.permissions.exceptions import (
    PermissionsRepositoryError,
    PermissionNotFoundError,
    PermissionsServiceError,
    DuplicatePermissionError,
    ValidationError,
)


class PermissionsService:
    def __init__(self, repository: PermissionsRepository):
        self._repository = repository

    def create_permission(self, data: dict) -> Permission:
        permission_code = data.get("permission_code")
        permission_name = data.get("permission_name")
        description = data.get("description")
        action = data.get("action") or PermissionAction.READ

        if not permission_code or not permission_name:
            raise ValidationError(
                "Missing required fields: permission_code and permission_name"
            )

        try:
            if self._repository.exists_by_permission_code(permission_code):
                raise DuplicatePermissionError(
                    f"Permission code '{permission_code}' is already in use."
                )
            if self._repository.exists_by_permission_name(permission_name):
                raise DuplicatePermissionError(
                    f"Permission name '{permission_name}' is already in use."
                )
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Repository validation failed: {e}") from e

        try:
            permission = Permission(
                permission_code=permission_code,
                permission_name=permission_name,
                description=description,
                action=action,
            )
            return self._repository.create(permission)
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Failed to create permission: {e}") from e

    def get_permission(self, permission_id: UUID) -> Permission:
        try:
            permission = self._repository.get_by_id(permission_id)
            if not permission:
                raise PermissionNotFoundError(f"Permission {permission_id} not found")
            return permission
        except PermissionsRepositoryError as e:
            if isinstance(e, PermissionNotFoundError):
                raise
            raise PermissionsServiceError(f"Failed to retrieve permission: {e}") from e

    def list_permissions(
        self, skip: int = 0, limit: int = 100, search: str = ""
    ) -> tuple[Sequence[Permission], int]:
        try:
            if search:
                perms = self._repository.search_permissions(
                    search, offset=skip, limit=limit
                )
                total = self._repository.count_search_permissions(search)
                return perms, total
            else:
                perms = self._repository.list(offset=skip, limit=limit)
                total = self._repository.count()
                return perms, total
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Failed to list permissions: {e}") from e

    def update_permission(self, permission_id: UUID, data: dict) -> Permission:
        permission = self.get_permission(permission_id)

        if (
            "permission_name" in data
            and data["permission_name"] != permission.permission_name
        ):
            try:
                if self._repository.exists_by_permission_name(data["permission_name"]):
                    raise DuplicatePermissionError("Permission name is already in use.")
            except PermissionsRepositoryError as e:
                raise PermissionsServiceError(f"Validation failed: {e}") from e
            permission.permission_name = data["permission_name"]

        if "description" in data:
            permission.description = data["description"]

        if "action" in data:
            permission.action = data["action"]

        if "status" in data:
            permission.status = data["status"]

        try:
            return self._repository.update(permission)
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Failed to update permission: {e}") from e

    def patch_permission(self, permission_id: UUID, data: dict) -> Permission:
        return self.update_permission(permission_id, data)

    def delete_permission(self, permission_id: UUID) -> bool:
        permission = self.get_permission(permission_id)

        try:
            return self._repository.delete(permission_id)
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Failed to delete permission: {e}") from e

    def search_permissions(self, query: str) -> Sequence[Permission]:
        try:
            return self._repository.search(permission_name=query, limit=100)
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Failed to search permissions: {e}") from e

    def count_permissions(self) -> int:
        try:
            return self._repository.count()
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Failed to count permissions: {e}") from e

    def activate_permission(self, permission_id: UUID) -> Permission:
        self.get_permission(permission_id)
        try:
            return self._repository.activate(permission_id)
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Failed to activate permission: {e}") from e

    def deactivate_permission(self, permission_id: UUID) -> Permission:
        self.get_permission(permission_id)
        try:
            return self._repository.deactivate(permission_id)
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(
                f"Failed to deactivate permission: {e}"
            ) from e
