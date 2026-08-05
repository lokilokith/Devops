"""Vault Repository Contracts and Implementation."""

from __future__ import annotations

from typing import Optional, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.vault.domain import Secret, SecretMetadata, SecretVersion
from app.vault.models import VaultSecret, VaultSecretVersion


class SecretRepository(Protocol):
    """Abstract persistence contract for the Secret aggregate."""

    def save(self, secret: Secret) -> None:
        """Save a new or updated Secret aggregate. Handles optimistic locking."""
        ...

    def find_by_id(self, id: UUID) -> Optional[Secret]:
        """Load a Secret aggregate by its ID."""
        ...

    def find_by_resource(self, resource_id: UUID) -> Optional[Secret]:
        """Load a Secret aggregate by its linked Resource ID."""
        ...

    def exists(self, resource_id: UUID) -> bool:
        """Check if a Secret exists for a given Resource ID."""
        ...

    def delete(self, id: UUID) -> None:
        """Delete a Secret by ID."""
        ...


class SqlAlchemyVaultRepository:
    """SQLAlchemy implementation of the SecretRepository."""

    def __init__(self, session: Session):
        self._session = session

    def _to_domain(self, model: VaultSecret) -> Secret:
        secret = Secret(
            id=model.id,
            resource_id=model.resource_id,
            status=model.status,
            current_version_id=model.current_version_id,
            row_version=model.row_version,
            created_at=model.created_at,
            updated_at=model.updated_at,
            versions=[],
        )
        for v_model in model.versions:
            metadata = SecretMetadata(
                key_version=v_model.key_version,
                algorithm=v_model.algorithm,
                nonce=v_model.nonce,
                encryption_context=v_model.encryption_context,
            )
            version = SecretVersion(
                id=v_model.id,
                secret_id=v_model.secret_id,
                encrypted_dek=v_model.encrypted_dek,
                encrypted_payload=v_model.encrypted_payload,
                metadata=metadata,
                created_at=v_model.created_at,
                created_by=v_model.created_by,
            )
            secret.versions.append(version)
        return secret

    def save(self, secret: Secret) -> None:
        model = self._session.get(VaultSecret, secret.id)
        if not model:
            # Insert new, defer current_version_id to avoid FK cycle
            model = VaultSecret(
                id=secret.id,
                resource_id=secret.resource_id,
                status=secret.status,
                row_version=secret.row_version,
                current_version_id=None,
                created_at=secret.created_at,
                updated_at=secret.updated_at,
            )
            self._session.add(model)
            self._session.flush() # Insert parent record first
        else:
            # Check optimistic lock
            if model.row_version >= secret.row_version:
                raise ValueError("Optimistic concurrency failure: row_version mismatch.")

            # Update existing
            model.status = secret.status
            model.row_version = secret.row_version
            model.updated_at = secret.updated_at

        # Upsert versions
        existing_version_ids = {v.id for v in model.versions} if model.versions else set()
        for v in secret.versions:
            if v.id not in existing_version_ids:
                v_model = VaultSecretVersion(
                    id=v.id,
                    secret_id=v.secret_id,
                    encrypted_dek=v.encrypted_dek,
                    encrypted_payload=v.encrypted_payload,
                    key_version=v.metadata.key_version,
                    algorithm=v.metadata.algorithm,
                    nonce=v.metadata.nonce,
                    encryption_context=v.metadata.encryption_context,
                    created_by=v.created_by,
                    created_at=v.created_at,
                    updated_at=v.created_at,
                )
                model.versions.append(v_model)

        self._session.flush() # Flush the versions

        # Now safe to update current_version_id since version exists
        model.current_version_id = secret.current_version_id
        self._session.flush()

    def find_by_id(self, id: UUID) -> Optional[Secret]:
        model = self._session.get(VaultSecret, id)
        return self._to_domain(model) if model else None

    def find_by_resource(self, resource_id: UUID) -> Optional[Secret]:
        model = self._session.execute(
            select(VaultSecret).where(VaultSecret.resource_id == resource_id)
        ).scalar_one_or_none()
        return self._to_domain(model) if model else None

    def exists(self, resource_id: UUID) -> bool:
        result = self._session.execute(
            select(VaultSecret.id).where(VaultSecret.resource_id == resource_id)
        ).scalar_one_or_none()
        return result is not None

    def delete(self, id: UUID) -> None:
        model = self._session.get(VaultSecret, id)
        if model:
            self._session.delete(model)
            self._session.flush()
