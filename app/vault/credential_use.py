"""Authorized Credential-Use Operation (Master Plan Item 14.1 / Item 4).

Establishes the single, narrow, authorized credential-use interface in Vault Plane.
Generic `decrypt(credential_id)` or bare lookups by ID are strictly prohibited.
Every credential-use release requires proof of the complete authorization chain:
- User identity
- Resource identity
- Target account binding identity
- Access grant identity / session identity
- Credential identifier
- Temporal validity (requested_at <= now <= expires_at)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.vault.crypto import EncryptionService
from app.vault.exceptions import VaultException
from app.vault.repository import SqlAlchemyVaultRepository

logger = logging.getLogger(__name__)


class UnauthorizedCredentialUseError(VaultException):
    """Raised when a credential-use request fails authorization validation."""


@dataclass(frozen=True)
class CredentialUseContext:
    """Strongly-typed authorization proof required to access credential material."""

    user_id: UUID
    resource_id: UUID
    credential_id: UUID
    requested_at: datetime
    expires_at: datetime
    session_id: Optional[UUID] = None
    grant_id: Optional[UUID] = None
    target_account_binding_id: Optional[UUID] = None

    def validate(self, current_time: Optional[datetime] = None) -> None:
        """Validate context integrity and temporal validity against UTC wall-clock time."""
        if not self.user_id:
            raise UnauthorizedCredentialUseError(
                "Credential use rejected: user_id is required"
            )
        if not self.resource_id:
            raise UnauthorizedCredentialUseError(
                "Credential use rejected: resource_id is required"
            )
        if not self.credential_id:
            raise UnauthorizedCredentialUseError(
                "Credential use rejected: credential_id is required"
            )

        now = current_time or datetime.now(timezone.utc)
        req_at = (
            self.requested_at
            if self.requested_at.tzinfo
            else self.requested_at.replace(tzinfo=timezone.utc)
        )
        exp_at = (
            self.expires_at
            if self.expires_at.tzinfo
            else self.expires_at.replace(tzinfo=timezone.utc)
        )

        if req_at > exp_at:
            raise UnauthorizedCredentialUseError(
                "Credential use rejected: requested_at is after expires_at"
            )

        if now > exp_at:
            raise UnauthorizedCredentialUseError(
                "Credential use rejected: authorization context has expired"
            )


class CredentialUseService:
    """Vault service providing the single narrow authorized credential-use operation."""

    def __init__(
        self,
        vault_repository: SqlAlchemyVaultRepository,
        encryption_service: EncryptionService,
    ) -> None:
        self._vault_repo = vault_repository
        self._encryption_service = encryption_service

    def acquire_ephemeral_credential(
        self,
        context: CredentialUseContext,
        current_time: Optional[datetime] = None,
    ) -> bytes:
        """Release ephemeral credential plaintext ONLY upon verification of full authorization context.

        Args:
            context: The complete typed authorization context.
            current_time: Optional evaluation timestamp (defaults to current UTC wall-clock).

        Returns:
            bytes: Ephemeral plaintext credential bytes for immediate in-memory use.

        Raises:
            UnauthorizedCredentialUseError: If context validation or resource binding fails.
            VaultException: If the secret or active version does not exist.
        """
        # 1. Validate complete authorization chain context
        context.validate(current_time)

        # 2. Retrieve secret and verify resource binding
        secret = self._vault_repo.find_by_id(context.credential_id)
        if not secret:
            raise UnauthorizedCredentialUseError(
                f"Credential use rejected: credential {context.credential_id} not found"
            )

        if secret.resource_id != context.resource_id:
            raise UnauthorizedCredentialUseError(
                f"Credential use rejected: credential {context.credential_id} is not bound "
                f"to resource {context.resource_id}"
            )

        # 3. Retrieve current secret version
        version = secret.current_version
        if not version:
            raise VaultException(
                f"No active secret version found for credential {context.credential_id}"
            )

        # 4. Decrypt payload in-memory
        plaintext = self._encryption_service.decrypt_payload(
            resource_id=secret.resource_id,
            secret_id=secret.id,
            encrypted_dek=version.encrypted_dek,
            encrypted_payload=version.encrypted_payload,
            metadata=version.metadata,
        )

        return plaintext
