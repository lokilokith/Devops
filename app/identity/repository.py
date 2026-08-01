"""Identity repository for OpsForge.

This module provides database access logic for User entities within the PAM platform.
"""

from __future__ import annotations

from typing import Sequence, TypeVar
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.identity.exceptions import IdentityRepositoryError, UserNotFoundError
from app.identity.models import User, UserStatus

T = TypeVar("T")


class IdentityRepository:
    """Repository managing persistence and retrieval operations for User entities."""

    def __init__(self, session: Session) -> None:
        """Initialize repository with a SQLAlchemy session.

        Args:
            session: Active SQLAlchemy database session.
        """
        self._session = session

    def _get_user_or_raise(self, user_id: UUID) -> User:
        """Fetch a User entity by ID or raise UserNotFoundError.

        Args:
            user_id: Unique user identifier.

        Returns:
            User instance.

        Raises:
            UserNotFoundError: If the user does not exist.
        """
        user = self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(f"User with ID '{user_id}' not found.")
        return user

    def _commit_and_refresh(self, entity: T) -> T:
        """Commit session changes and refresh the given database entity.

        Args:
            entity: Domain entity to commit and refresh.

        Returns:
            Refreshed domain entity instance.
        """
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def create_user(self, user: User) -> User:
        """Persist a new User entity.

        Args:
            user: Unpersisted User instance.

        Returns:
            The created User instance.

        Raises:
            IdentityRepositoryError: If the database operation fails.
        """
        try:
            self._session.add(user)
            return self._commit_and_refresh(user)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise IdentityRepositoryError(
                "Failed to create user database record."
            ) from err

    def get_by_id(self, user_id: UUID) -> User | None:
        """Fetch a User entity by primary key ID.

        Args:
            user_id: Unique user identifier.

        Returns:
            User instance if found, None otherwise.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            return self._session.get(User, user_id)
        except SQLAlchemyError as err:
            raise IdentityRepositoryError("Failed to retrieve user by ID.") from err

    def get_by_username(self, username: str) -> User | None:
        """Fetch a User entity by username.

        Args:
            username: User login name.

        Returns:
            User instance if found, None otherwise.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            stmt = select(User).where(User.username == username)
            return self._session.scalar(stmt)
        except SQLAlchemyError as err:
            raise IdentityRepositoryError(
                "Failed to retrieve user by username."
            ) from err

    def get_by_email(self, email: str) -> User | None:
        """Fetch a User entity by email address.

        Args:
            email: User email address.

        Returns:
            User instance if found, None otherwise.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            stmt = select(User).where(User.email == email)
            return self._session.scalar(stmt)
        except SQLAlchemyError as err:
            raise IdentityRepositoryError("Failed to retrieve user by email.") from err

    def list_users(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> Sequence[User]:
        """List users with pagination and deterministic ordering.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return (capped at 1000).
            include_deleted: Whether to include soft-deleted users.

        Returns:
            Sequence of User instances.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            bounded_limit = min(max(1, limit), 1000)
            stmt = select(User)
            if not include_deleted:
                stmt = stmt.where(User.status != UserStatus.ARCHIVED)
            stmt = stmt.order_by(User.username.asc()).offset(skip).limit(bounded_limit)
            return self._session.scalars(stmt).all()
        except SQLAlchemyError as err:
            raise IdentityRepositoryError("Failed to list users.") from err

    def update_user(self, user: User) -> User:
        """Persist state updates for a User entity.

        Handles merging detached objects into the active session cleanly.

        Args:
            user: User instance containing updated attributes.

        Returns:
            The persisted User instance.

        Raises:
            IdentityRepositoryError: If the database operation fails.
        """
        try:
            merged_user = self._session.merge(user)
            return self._commit_and_refresh(merged_user)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise IdentityRepositoryError("Failed to update user record.") from err

    def delete_user(self, user_id: UUID) -> bool:
        """Soft-delete a User entity by ID.

        Args:
            user_id: Unique user identifier.

        Returns:
            True if deleted, False if user not found or already deleted.

        Raises:
            IdentityRepositoryError: If the database operation fails.
        """
        try:
            user = self.get_by_id(user_id)
            if not user or user.status == UserStatus.ARCHIVED:
                return False

            user.status = UserStatus.ARCHIVED
            self._commit_and_refresh(user)
            return True
        except SQLAlchemyError as err:
            self._session.rollback()
            raise IdentityRepositoryError("Failed to soft-delete user record.") from err

    def exists_by_username(self, username: str) -> bool:
        """Check if a user exists with the given username.

        Args:
            username: Username to check.

        Returns:
            True if exists, False otherwise.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            stmt = select(exists().where(User.username == username))
            return bool(self._session.scalar(stmt))
        except SQLAlchemyError as err:
            raise IdentityRepositoryError(
                "Failed to check username existence."
            ) from err

    def exists_by_email(self, email: str) -> bool:
        """Check if a user exists with the given email address.

        Args:
            email: Email address to check.

        Returns:
            True if exists, False otherwise.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            stmt = select(exists().where(User.email == email))
            return bool(self._session.scalar(stmt))
        except SQLAlchemyError as err:
            raise IdentityRepositoryError("Failed to check email existence.") from err

    def exists_by_employee_id(
        self, employee_id: str, exclude_user_id: UUID | None = None
    ) -> bool:
        """Check if a user exists with the given employee ID.

        Args:
            employee_id: Employee ID to check.
            exclude_user_id: Optional user ID to exclude from the check.

        Returns:
            True if exists, False otherwise.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            from sqlalchemy import and_

            conditions = [User.employee_id == employee_id]
            if exclude_user_id:
                conditions.append(User.id != exclude_user_id)
            stmt = select(exists().where(and_(*conditions)))
            return bool(self._session.scalar(stmt))
        except SQLAlchemyError as err:
            raise IdentityRepositoryError(
                "Failed to check employee_id existence."
            ) from err

    def search_users(
        self, query: str, skip: int = 0, limit: int = 100
    ) -> Sequence[User]:
        """Search users by username, email, employee_id, or full_name.

        Args:
            query: The search string.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Sequence of User instances.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            from sqlalchemy import or_

            bounded_limit = min(max(1, limit), 1000)
            pattern = f"%{query}%"
            stmt = (
                select(User)
                .where(
                    or_(
                        User.username.ilike(pattern),
                        User.email.ilike(pattern),
                        User.employee_id.ilike(pattern),
                        User.full_name.ilike(pattern),
                    )
                )
                .order_by(User.username.asc())
                .offset(skip)
                .limit(bounded_limit)
            )
            return self._session.scalars(stmt).all()
        except SQLAlchemyError as err:
            raise IdentityRepositoryError("Failed to search users.") from err

    def count_users(self) -> int:
        """Count total users in the database.

        Returns:
            Total number of users.

        Raises:
            IdentityRepositoryError: If the database query fails.
        """
        try:
            from sqlalchemy import func

            stmt = select(func.count()).select_from(User)
            return self._session.scalar(stmt) or 0
        except SQLAlchemyError as err:
            raise IdentityRepositoryError("Failed to count users.") from err

    def activate_user(self, user_id: UUID) -> User:
        """Activate a User entity.

        Args:
            user_id: Unique user identifier.

        Returns:
            Updated User instance.

        Raises:
            UserNotFoundError: If the user does not exist.
            IdentityRepositoryError: If the database operation fails.
        """
        try:
            user = self._get_user_or_raise(user_id)
            user.status = UserStatus.ACTIVE
            return self._commit_and_refresh(user)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise IdentityRepositoryError("Failed to activate user.") from err

    def deactivate_user(self, user_id: UUID) -> User:
        """Deactivate a User entity.

        Args:
            user_id: Unique user identifier.

        Returns:
            Updated User instance.

        Raises:
            UserNotFoundError: If the user does not exist.
            IdentityRepositoryError: If the database operation fails.
        """
        try:
            user = self._get_user_or_raise(user_id)
            user.status = UserStatus.DISABLED
            return self._commit_and_refresh(user)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise IdentityRepositoryError("Failed to deactivate user.") from err

    def lock_user(self, user_id: UUID) -> User:
        """Lock a User entity.

        Args:
            user_id: Unique user identifier.

        Returns:
            Updated User instance.

        Raises:
            UserNotFoundError: If the user does not exist.
            IdentityRepositoryError: If the database operation fails.
        """
        try:
            user = self._get_user_or_raise(user_id)
            user.status = UserStatus.LOCKED
            return self._commit_and_refresh(user)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise IdentityRepositoryError("Failed to lock user.") from err

    def unlock_user(self, user_id: UUID) -> User:
        """Unlock a User entity.

        Args:
            user_id: Unique user identifier.

        Returns:
            Updated User instance.

        Raises:
            UserNotFoundError: If the user does not exist.
            IdentityRepositoryError: If the database operation fails.
        """
        try:
            user = self._get_user_or_raise(user_id)
            user.status = UserStatus.ACTIVE
            return self._commit_and_refresh(user)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise IdentityRepositoryError("Failed to unlock user.") from err

    def count_search_users(self, query: str) -> int:
        try:
            from sqlalchemy import func, or_

            pattern = f"%{query}%"
            stmt = (
                select(func.count())
                .select_from(User)
                .where(
                    or_(
                        User.username.ilike(pattern),
                        User.email.ilike(pattern),
                        User.employee_id.ilike(pattern),
                        User.full_name.ilike(pattern),
                    )
                )
            )
            return self._session.scalar(stmt) or 0
        except SQLAlchemyError as err:
            raise IdentityRepositoryError("Failed to count searched users.") from err


__all__ = [
    "IdentityRepository",
]
