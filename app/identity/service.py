"""Identity feature service layer."""
from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app.identity.repository import IdentityRepository
from app.identity.models import User
from app.identity.exceptions import (
    IdentityRepositoryError,
    UserNotFoundError,
    IdentityServiceError,
    DuplicateUserError,
    ValidationError
)
from app.auth.service import AuthService

class IdentityService:
    def __init__(self, repository: IdentityRepository, auth_service: AuthService):
        self._repository = repository
        self._auth_service = auth_service
        
    def _validate_duplicate_employee_id(self, employee_id: str, exclude_user_id: UUID | None = None) -> None:
        """In-memory check for duplicate employee_id since repository doesn't expose it."""
        skip = 0
        while True:
            try:
                batch = self._repository.list_users(skip=skip, limit=1000)
            except IdentityRepositoryError as e:
                raise IdentityServiceError(f"Failed to fetch users for validation: {e}") from e
                
            if not batch:
                break
                
            for user in batch:
                if user.employee_id == employee_id:
                    if exclude_user_id and user.id == exclude_user_id:
                        continue
                    raise DuplicateUserError(f"Employee ID '{employee_id}' is already in use.")
            skip += 1000

    def create_user(self, data: dict) -> User:
        username = data.get("username")
        email = data.get("email")
        employee_id = data.get("employee_id")
        password = data.get("password")
        
        if not username or not email or not employee_id or not password:
            raise ValidationError("Missing required fields")

        try:
            if self._repository.exists_by_username(username):
                raise DuplicateUserError(f"Username '{username}' is already in use.")
            if self._repository.exists_by_email(email):
                raise DuplicateUserError(f"Email '{email}' is already in use.")
        except IdentityRepositoryError as e:
            raise IdentityServiceError(f"Repository validation failed: {e}") from e
            
        self._validate_duplicate_employee_id(employee_id)
        
        try:
            user = User(
                username=username,
                email=email,
                employee_id=employee_id,
                full_name=data.get("full_name", ""),
                title=data.get("title"),
                manager_user_id=data.get("manager_user_id")
            )
            # Hash password using auth service
            user.password_hash = self._auth_service.hash_password(password)
            
            return self._repository.create_user(user)
        except IdentityRepositoryError as e:
            raise IdentityServiceError(f"Failed to create user: {e}") from e

    def get_user(self, user_id: UUID) -> User:
        try:
            user = self._repository.get_by_id(user_id)
            if not user:
                raise UserNotFoundError(f"User {user_id} not found")
            return user
        except IdentityRepositoryError as e:
            if isinstance(e, UserNotFoundError):
                raise
            raise IdentityServiceError(f"Failed to retrieve user: {e}") from e

    def list_users(self, skip: int = 0, limit: int = 100) -> Sequence[User]:
        try:
            return self._repository.list_users(skip=skip, limit=limit)
        except IdentityRepositoryError as e:
            raise IdentityServiceError(f"Failed to list users: {e}") from e

    def update_user(self, user_id: UUID, data: dict) -> User:
        user = self.get_user(user_id)
        
        # We can't update username, email, employee_id completely freely without checks
        # But wait, usually update replaces all fields.
        if "username" in data and data["username"] != user.username:
            try:
                if self._repository.exists_by_username(data["username"]):
                    raise DuplicateUserError("Username is already in use.")
            except IdentityRepositoryError as e:
                raise IdentityServiceError(f"Validation failed: {e}") from e
            user.username = data["username"]
            
        if "email" in data and data["email"] != user.email:
            try:
                if self._repository.exists_by_email(data["email"]):
                    raise DuplicateUserError("Email is already in use.")
            except IdentityRepositoryError as e:
                raise IdentityServiceError(f"Validation failed: {e}") from e
            user.email = data["email"]
            
        if "employee_id" in data and data["employee_id"] != user.employee_id:
            self._validate_duplicate_employee_id(data["employee_id"], exclude_user_id=user_id)
            user.employee_id = data["employee_id"]
            
        if "full_name" in data:
            user.full_name = data["full_name"]
        if "title" in data:
            user.title = data["title"]
        if "status" in data:
            # Assuming enum mapping happens elsewhere or we just assign string
            user.status = data["status"]

        if "password" in data and data["password"]:
            user.password_hash = self._auth_service.hash_password(data["password"])

        try:
            return self._repository.update_user(user)
        except IdentityRepositoryError as e:
            raise IdentityServiceError(f"Failed to update user: {e}") from e

    def patch_user(self, user_id: UUID, data: dict) -> User:
        return self.update_user(user_id, data)

    def delete_user(self, user_id: UUID) -> bool:
        try:
            return self._repository.delete_user(user_id)
        except IdentityRepositoryError as e:
            raise IdentityServiceError(f"Failed to delete user: {e}") from e

    def search_users(self, query: str) -> list[User]:
        if not query:
            return []
            
        query = query.lower()
        results = []
        skip = 0
        while True:
            try:
                batch = self._repository.list_users(skip=skip, limit=1000)
            except IdentityRepositoryError as e:
                raise IdentityServiceError(f"Failed to fetch users for search: {e}") from e
                
            if not batch:
                break
                
            for user in batch:
                if (query in user.username.lower() or 
                    query in user.email.lower() or 
                    query in user.employee_id.lower() or 
                    query in (user.full_name or "").lower()):
                    results.append(user)
                    
            skip += 1000
        return results

    def count_users(self) -> int:
        count = 0
        skip = 0
        while True:
            try:
                batch = self._repository.list_users(skip=skip, limit=1000)
            except IdentityRepositoryError as e:
                raise IdentityServiceError(f"Failed to fetch users for count: {e}") from e
                
            if not batch:
                break
            count += len(batch)
            skip += 1000
        return count
