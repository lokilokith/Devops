"""Policy Engine repository for OpsForge."""

from __future__ import annotations

from typing import Sequence, TypeVar
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.policy_engine.exceptions import PolicyNotFoundError, PolicyRepositoryError
from app.policy_engine.models import AccessPolicy
from app.shared.database import BaseModel

T = TypeVar("T", bound=BaseModel)


class PolicyRepository:
    """Repository managing persistence and retrieval of AccessPolicy entities."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _commit_and_refresh(self, entity: T) -> T:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def _commit_only(self) -> None:
        self._session.commit()

    @staticmethod
    def _normalize_pagination(limit: int, offset: int) -> tuple[int, int]:
        bounded_limit = min(max(1, limit), 1000)
        normalized_offset = max(0, offset)
        return bounded_limit, normalized_offset

    def create(self, policy: AccessPolicy) -> AccessPolicy:
        try:
            self._session.add(policy)
            return self._commit_and_refresh(policy)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError(
                "Failed to create policy database record."
            ) from err

    def get_by_id(self, policy_id: UUID) -> AccessPolicy | None:
        try:
            stmt = select(AccessPolicy).where(AccessPolicy.id == policy_id)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError("Failed to retrieve policy by ID.") from err

    def get_by_name(self, name: str) -> AccessPolicy | None:
        try:
            stmt = select(AccessPolicy).where(AccessPolicy.name == name.strip())
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError("Failed to retrieve policy by name.") from err

    def exists_by_name(self, name: str) -> bool:
        try:
            stmt = select(exists().where(AccessPolicy.name == name.strip()))
            return bool(self._session.execute(stmt).scalar())
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError(
                "Failed to check policy name existence."
            ) from err

    def list_policies(
        self,
        *,
        enabled: bool | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[AccessPolicy]:
        try:
            bounded_limit, normalized_offset = self._normalize_pagination(limit, offset)
            stmt = select(AccessPolicy)

            if enabled is not None:
                stmt = stmt.where(AccessPolicy.enabled == enabled)

            stmt = stmt.order_by(
                AccessPolicy.priority.desc(), AccessPolicy.created_at.desc()
            )
            stmt = stmt.offset(normalized_offset).limit(bounded_limit)

            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError("Failed to list policies.") from err

    def count_policies(self, *, enabled: bool | None = None) -> int:
        try:
            stmt = select(func.count(AccessPolicy.id))
            if enabled is not None:
                stmt = stmt.where(AccessPolicy.enabled == enabled)
            return self._session.execute(stmt).scalar_one()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError("Failed to count policies.") from err

    def update(self, policy: AccessPolicy) -> AccessPolicy:
        try:
            merged_policy = self._session.merge(policy)
            return self._commit_and_refresh(merged_policy)
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError("Failed to update policy record.") from err

    def delete(self, policy_id: UUID) -> bool:
        try:
            policy = self.get_by_id(policy_id)
            if not policy:
                raise PolicyNotFoundError(f"Policy with ID '{policy_id}' not found.")

            # Policy dependencies checks could be implemented here.
            # E.g., check if policy is currently attached to active requests/sessions.

            self._session.delete(policy)
            self._commit_only()
            return True
        except PolicyNotFoundError:
            raise
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError("Failed to delete policy record.") from err

    def get_active_policies(self) -> Sequence[AccessPolicy]:
        """Fetch all currently enabled policies, ordered by priority."""
        try:
            stmt = (
                select(AccessPolicy)
                .where(AccessPolicy.enabled.is_(True))
                .order_by(AccessPolicy.priority.desc())
            )
            return self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as err:
            self._session.rollback()
            raise PolicyRepositoryError("Failed to fetch active policies.") from err


__all__ = ["PolicyRepository"]
