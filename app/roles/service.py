"""Roles feature service layer."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app.roles.repository import RolesRepository
from app.roles.models import Role, RoleType
from app.roles.exceptions import (
    RolesRepositoryError,
    RoleNotFoundError,
    RolesServiceError,
    DuplicateRoleError,
    ValidationError,
)


class RolesService:
    def __init__(self, repository: RolesRepository):
        self._repository = repository

    def create_role(self, data: dict) -> Role:
        role_code = data.get("role_code")
        role_name = data.get("role_name")
        description = data.get("description")

        if not role_code or not role_name:
            raise ValidationError("Missing required fields: role_code and role_name")

        try:
            if self._repository.exists_by_role_code(role_code):
                raise DuplicateRoleError(f"Role code '{role_code}' is already in use.")
            if self._repository.exists_by_role_name(role_name):
                raise DuplicateRoleError(f"Role name '{role_name}' is already in use.")
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Repository validation failed: {e}") from e

        try:
            role = Role(
                role_code=role_code, role_name=role_name, description=description
            )
            return self._repository.create(role)
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Failed to create role: {e}") from e

    def get_role(self, role_id: UUID) -> Role:
        try:
            role = self._repository.get_by_id(role_id)
            if not role:
                raise RoleNotFoundError(f"Role {role_id} not found")
            return role
        except RolesRepositoryError as e:
            if isinstance(e, RoleNotFoundError):
                raise
            raise RolesServiceError(f"Failed to retrieve role: {e}") from e

    def list_roles(
        self, skip: int = 0, limit: int = 100, search: str = ""
    ) -> tuple[Sequence[Role], int]:
        try:
            if search:
                roles = self._repository.search_roles(search, offset=skip, limit=limit)
                total = self._repository.count_search_roles(search)
                return roles, total
            else:
                roles = self._repository.list(offset=skip, limit=limit)
                total = self._repository.count()
                return roles, total
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Failed to list roles: {e}") from e

    def update_role(self, role_id: UUID, data: dict) -> Role:
        role = self.get_role(role_id)

        if "role_name" in data and data["role_name"] != role.role_name:
            try:
                if self._repository.exists_by_role_name(data["role_name"]):
                    raise DuplicateRoleError("Role name is already in use.")
            except RolesRepositoryError as e:
                raise RolesServiceError(f"Validation failed: {e}") from e
            role.role_name = data["role_name"]

        if "description" in data:
            role.description = data["description"]

        if "status" in data:
            role.status = data["status"]

        try:
            return self._repository.update(role)
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Failed to update role: {e}") from e

    def patch_role(self, role_id: UUID, data: dict) -> Role:
        return self.update_role(role_id, data)

    def delete_role(self, role_id: UUID) -> bool:
        role = self.get_role(role_id)

        if str(role.role_type.value) == RoleType.SYSTEM.value:
            raise ValidationError("Cannot delete system roles.")

        try:
            return self._repository.delete(role_id)
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Failed to delete role: {e}") from e

    def search_roles(self, query: str) -> Sequence[Role]:
        try:
            # We will pass query to role_name and role_code.
            # In RolesRepository search, it accepts role_code and role_name.
            # Usually search takes those. Let's just pass role_name for now.
            return self._repository.search(role_name=query, limit=100)
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Failed to search roles: {e}") from e

    def count_roles(self) -> int:
        try:
            return self._repository.count()
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Failed to count roles: {e}") from e

    def activate_role(self, role_id: UUID) -> Role:
        # Check if role exists
        self.get_role(role_id)
        try:
            return self._repository.activate(role_id)
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Failed to activate role: {e}") from e

    def deactivate_role(self, role_id: UUID) -> Role:
        # Check if role exists
        self.get_role(role_id)
        try:
            return self._repository.deactivate(role_id)
        except RolesRepositoryError as e:
            raise RolesServiceError(f"Failed to deactivate role: {e}") from e
