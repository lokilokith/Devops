"""UserRoles repository for OpsForge.

This module provides database access logic
for UserRole entities.
"""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.user_roles.exceptions import (
    UserRoleAlreadyExistsError,
    UserRoleNotFoundError,
    UserRolesRepositoryError,
)
from app.roles.models import Role, UserRole
from app.identity.models import User

class UserRolesRepository:
    """
    Repository managing persistence and retrieval
    operations for UserRole association entities.
    """

    def __init__(self, session: Session) -> None:
        """Initialize repository with a SQLAlchemy session.

        Args:
            session: Active SQLAlchemy database session.
        """
        self._session = session

    def assign_role_to_user(
        self, user_id: UUID, role_id: UUID, assigned_by_user_id: UUID | None = None
    ) -> UserRole:
        """Assign a role to a user.

        Args:
            user_id: Unique user identifier.
            role_id: Unique role identifier.
            assigned_by_user_id: Optional ID of the user creating the assignment.

        Returns:
            The created UserRole instance.

        Raises:
            UserRoleAlreadyExistsError: If association already exists.
            UserRolesRepositoryError: If database operation fails.
        """
        if self.exists(user_id, role_id):
            raise UserRoleAlreadyExistsError("Role is already assigned to the user.")
        try:
            ur = UserRole(
                user_id=user_id,
                role_id=role_id,
                assigned_by_user_id=assigned_by_user_id,
            )
            self._session.add(ur)
            self._session.commit()
            self._session.refresh(ur)
            return ur
        except SQLAlchemyError as err:
            self._session.rollback()
            raise UserRolesRepositoryError("Failed to assign role to user.") from err

    def remove_role_from_user(self, user_id: UUID, role_id: UUID) -> bool:
        """Remove a role from a user.

        Args:
            user_id: Unique user identifier.
            role_id: Unique role identifier.

        Returns:
            True if removed successfully.

        Raises:
            UserRoleNotFoundError: If association does not exist.
            UserRolesRepositoryError: If database operation fails.
        """
        try:
            stmt = select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
            )
            ur = self._session.execute(stmt).scalar_one_or_none()
            if not ur:
                raise UserRoleNotFoundError("UserRole association not found.")
            
            self._session.delete(ur)
            self._session.commit()
            return True
        except UserRoleNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise UserRolesRepositoryError("Failed to remove role from user.") from err

    def get_assignment(self, user_id: UUID, role_id: UUID) -> UserRole | None:
        """Get a specific UserRole assignment.

        Args:
            user_id: Unique user identifier.
            role_id: Unique role identifier.

        Returns:
            UserRole instance if found, None otherwise.

        Raises:
            UserRolesRepositoryError: If database query fails.
        """
        try:
            stmt = select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
            )
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise UserRolesRepositoryError("Failed to get assignment.") from err

    def exists(self, user_id: UUID, role_id: UUID) -> bool:
        """Check if a specific role is assigned to a specific user.

        Args:
            user_id: Unique user identifier.
            role_id: Unique role identifier.

        Returns:
            True if assigned, False otherwise.

        Raises:
            UserRolesRepositoryError: If database query fails.
        """
        try:
            stmt = select(exists().where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
            ))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise UserRolesRepositoryError("Failed to check existence.") from err

    def list_roles_for_user(self, user_id: UUID) -> Sequence[Role]:
        """List all roles assigned to a user.

        Args:
            user_id: Unique user identifier.

        Returns:
            Sequence of Role instances.

        Raises:
            UserRolesRepositoryError: If database query fails.
        """
        try:
            stmt = (
                select(Role)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
                .order_by(UserRole.assigned_at.desc())
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise UserRolesRepositoryError("Failed to list roles for user.") from err

    def list_users_for_role(self, role_id: UUID) -> Sequence[User]:
        """List all users assigned to a role.

        Args:
            role_id: Unique role identifier.

        Returns:
            Sequence of User instances.

        Raises:
            UserRolesRepositoryError: If database query fails.
        """
        try:
            stmt = (
                select(User)
                .join(UserRole, UserRole.user_id == User.id)
                .where(UserRole.role_id == role_id)
                .order_by(UserRole.assigned_at.desc())
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise UserRolesRepositoryError("Failed to list users for role.") from err

    def count_roles_for_user(self, user_id: UUID) -> int:
        """Count how many roles a user has.

        Args:
            user_id: Unique user identifier.

        Returns:
            Count of roles.

        Raises:
            UserRolesRepositoryError: If database query fails.
        """
        try:
            stmt = select(func.count(UserRole.role_id)).where(UserRole.user_id == user_id)
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise UserRolesRepositoryError("Failed to count roles for user.") from err

    def count_users_for_role(self, role_id: UUID) -> int:
        """Count how many users have a specific role.

        Args:
            role_id: Unique role identifier.

        Returns:
            Count of users.

        Raises:
            UserRolesRepositoryError: If database query fails.
        """
        try:
            stmt = select(func.count(UserRole.user_id)).where(UserRole.role_id == role_id)
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise UserRolesRepositoryError("Failed to count users for role.") from err

__all__ = ["UserRolesRepository"]
