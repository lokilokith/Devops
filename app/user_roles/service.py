"""UserRoles feature service layer."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app.identity.models import User
from app.identity.repository import IdentityRepository
from app.roles.models import Role, UserRole
from app.roles.repository import RolesRepository
from app.user_roles.exceptions import (
    UserRoleAlreadyExistsError,
    UserRoleNotFoundError,
    UserRolesRepositoryError,
    UserRolesServiceError,
    ValidationError,
)
from app.user_roles.repository import UserRolesRepository


class UserRoleService:
    def __init__(
        self,
        repository: UserRolesRepository,
        roles_repository: RolesRepository,
        users_repository: IdentityRepository,
    ):
        self._repository = repository
        self._roles_repository = roles_repository
        self._users_repository = users_repository

    def assign_role(
        self, user_id: UUID, role_id: UUID, assigned_by_user_id: UUID | None = None
    ) -> UserRole:
        try:
            user = self._users_repository.get_by_id(user_id)
            if not user:
                raise ValidationError("User does not exist.")
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise UserRolesServiceError("Error checking user.") from e

        try:
            role = self._roles_repository.get_by_id(role_id)
            if not role:
                raise ValidationError("Role does not exist.")
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise UserRolesServiceError("Error checking role.") from e

        try:
            from app.notifications.events import role_provisioned

            ur = self._repository.assign_role_to_user(
                user_id, role_id, assigned_by_user_id
            )

            role_provisioned.send(
                self,
                payload={
                    "event": "role_provisioned",
                    "actor_id": (
                        str(assigned_by_user_id) if assigned_by_user_id else "system"
                    ),
                    "recipient_id": str(user_id),
                    "title": "Role Provisioned",
                    "message": f"You have been assigned the role {role.role_name}.",
                    "type": "role_provisioned",
                    "priority": "normal",
                },
            )
            return ur
        except UserRoleAlreadyExistsError as e:
            raise ValidationError(str(e)) from e
        except UserRolesRepositoryError as e:
            raise UserRolesServiceError(f"Failed to assign role: {e}") from e

    def remove_role(self, user_id: UUID, role_id: UUID) -> bool:
        try:
            return self._repository.remove_role_from_user(user_id, role_id)
        except UserRoleNotFoundError as e:
            raise ValidationError(str(e)) from e
        except UserRolesRepositoryError as e:
            raise UserRolesServiceError(f"Failed to remove role: {e}") from e

    def list_roles_for_user(self, user_id: UUID) -> Sequence[Role]:
        try:
            return self._repository.list_roles_for_user(user_id)
        except UserRolesRepositoryError as e:
            raise UserRolesServiceError(f"Failed to list roles for user: {e}") from e

    def list_users_for_role(self, role_id: UUID) -> Sequence[User]:
        try:
            return self._repository.list_users_for_role(role_id)
        except UserRolesRepositoryError as e:
            raise UserRolesServiceError(f"Failed to list users for role: {e}") from e

    def exists(self, user_id: UUID, role_id: UUID) -> bool:
        try:
            return self._repository.exists(user_id, role_id)
        except UserRolesRepositoryError as e:
            raise UserRolesServiceError(f"Failed to check existence: {e}") from e

    def count_roles_for_user(self, user_id: UUID) -> int:
        try:
            return self._repository.count_roles_for_user(user_id)
        except UserRolesRepositoryError as e:
            raise UserRolesServiceError(f"Failed to count roles for user: {e}") from e

    def count_users_for_role(self, role_id: UUID) -> int:
        try:
            return self._repository.count_users_for_role(role_id)
        except UserRolesRepositoryError as e:
            raise UserRolesServiceError(f"Failed to count users for role: {e}") from e
