"""Vault Lifecycle Repository."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.vault_lifecycle.models import SecretRotationPolicy, RotationStatus


class SecretRotationPolicyRepository:
    """Repository for managing SecretRotationPolicy entities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_vault_secret_id(self, vault_secret_id: UUID) -> SecretRotationPolicy | None:
        stmt = select(SecretRotationPolicy).where(
            SecretRotationPolicy.vault_secret_id == vault_secret_id
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def find_by_id(self, policy_id: UUID) -> SecretRotationPolicy | None:
        stmt = select(SecretRotationPolicy).where(SecretRotationPolicy.id == policy_id)
        return self.session.execute(stmt).scalar_one_or_none()
        
    def save(self, policy: SecretRotationPolicy) -> None:
        self.session.add(policy)
        self.session.flush()

    def delete(self, policy: SecretRotationPolicy) -> None:
        self.session.delete(policy)
        self.session.flush()
