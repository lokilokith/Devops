"""Permissions feature service layer."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app.audit.models import AuditSeverity, AuditStatus
from app.audit.service import AuditService
from app.permissions.exceptions import (
    DuplicatePermissionError,
    PermissionNotFoundError,
    PermissionsRepositoryError,
    PermissionsServiceError,
    ValidationError,
)
from app.permissions.models import Permission, PermissionAction
from app.permissions.repository import PermissionsRepository


class PermissionsService:
    def __init__(
        self,
        repository: PermissionsRepository,
        audit_service: AuditService | None = None,
    ):
        self._repository = repository
        self._audit_service = audit_service

    def create_permission(self, data: dict, actor_id: UUID) -> Permission:
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
            created_permission = self._repository.create(permission)
            if self._audit_service and actor_id:
                self._audit_service.log_event(
                    actor_user_id=actor_id,
                    action="PERMISSION_CREATED",
                    resource_type="permissions",
                    resource_id=str(created_permission.id),
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                    details={
                        "permission_code": permission_code,
                        "permission_name": permission_name,
                    },
                )
                self._repository._session.commit()
            return created_permission
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

    def update_permission(
        self, permission_id: UUID, data: dict, actor_id: UUID
    ) -> Permission:
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
            updated_permission = self._repository.update(permission)
            if self._audit_service and actor_id:
                self._audit_service.log_event(
                    actor_user_id=actor_id,
                    action="PERMISSION_UPDATED",
                    resource_type="permissions",
                    resource_id=str(updated_permission.id),
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.INFO,
                )
                self._repository._session.commit()
            return updated_permission
        except PermissionsRepositoryError as e:
            raise PermissionsServiceError(f"Failed to update permission: {e}") from e

    def patch_permission(
        self, permission_id: UUID, data: dict, actor_id: UUID
    ) -> Permission:
        return self.update_permission(permission_id, data, actor_id)

    def delete_permission(self, permission_id: UUID, actor_id: UUID) -> bool:
        self.get_permission(permission_id)

        try:
            success = self._repository.delete(permission_id)
            if success and self._audit_service and actor_id:
                self._audit_service.log_event(
                    actor_user_id=actor_id,
                    action="PERMISSION_DELETED",
                    resource_type="permissions",
                    resource_id=str(permission_id),
                    status=AuditStatus.SUCCESS,
                    severity=AuditSeverity.HIGH,
                )
                self._repository._session.commit()
            return success
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
