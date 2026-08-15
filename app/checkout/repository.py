"""Checkout Repository."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.checkout.models import CredentialLease, LeaseStatus
from app.shared.exceptions import DatabaseOperationException


class CredentialLeaseRepository:
    """Repository for CredentialLease models."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, lease_id: UUID) -> Optional[CredentialLease]:
        return self._session.get(CredentialLease, lease_id)

    def save(self, lease: CredentialLease) -> None:
        try:
            self._session.add(lease)
            self._session.flush()
        except SQLAlchemyError as e:
            raise DatabaseOperationException(f"Failed to save credential lease: {e}") from e

    def get_active_lease_for_secret(self, secret_id: UUID) -> Optional[CredentialLease]:
        stmt = select(CredentialLease).where(
            CredentialLease.vault_secret_id == secret_id,
            CredentialLease.status == LeaseStatus.ACTIVE
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_active_leases_for_user(self, user_id: UUID) -> List[CredentialLease]:
        stmt = select(CredentialLease).where(
            CredentialLease.user_id == user_id,
            CredentialLease.status == LeaseStatus.ACTIVE
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_expired_active_leases(self, now) -> List[CredentialLease]:
        stmt = select(CredentialLease).where(
            CredentialLease.status == LeaseStatus.ACTIVE,
            CredentialLease.expires_at <= now
        )
        return list(self._session.execute(stmt).scalars().all())
