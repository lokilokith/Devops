"""Vault Domain Model and Services."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4


class SecretStatus(str, enum.Enum):
    ACTIVE = "active"
    CHECKED_OUT = "checked_out"
    ROTATING = "rotating"
    DISABLED = "disabled"
    TOMBSTONED = "tombstoned"
    DESYNCED = "desynced"
    JIT_EPHEMERAL = "jit_ephemeral"


@dataclass
class SecretMetadata:
    """Value Object for cryptographic metadata."""
    key_version: str
    algorithm: str
    nonce: str
    encryption_context: dict


@dataclass
class SecretVersion:
    """Entity representing a specific iteration of a secret's payload."""
    id: UUID
    secret_id: UUID
    encrypted_dek: bytes
    encrypted_payload: bytes
    metadata: SecretMetadata
    created_at: datetime
    created_by: UUID


@dataclass
class Secret:
    """Aggregate Root for a Privileged Secret."""
    id: UUID
    resource_id: UUID
    status: SecretStatus
    current_version_id: Optional[UUID]
    row_version: int
    created_at: datetime
    updated_at: datetime
    versions: List[SecretVersion] = field(default_factory=list)

    def add_version(self, version: SecretVersion) -> None:
        """Add a new version and update the pointer."""
        if version.secret_id != self.id:
            raise ValueError("Version belongs to a different secret.")
        self.versions.append(version)
        self.current_version_id = version.id
        # We don't automatically set ACTIVE here if it's called from complete_rotation or initialization,
        # but for backward compatibility with Phase 1, we preserve it.
        # However, for Phase 2, rotation lifecycle manages status.
        if self.status not in (SecretStatus.ROTATING, SecretStatus.ACTIVE, SecretStatus.JIT_EPHEMERAL, SecretStatus.CHECKED_OUT):
            self.status = SecretStatus.ACTIVE
        self.updated_at = datetime.now(timezone.utc)

    def checkout(self) -> None:
        if self.status != SecretStatus.ACTIVE:
            raise ValueError(f"Cannot checkout from {self.status.value} state.")
        self.status = SecretStatus.CHECKED_OUT
        self.updated_at = datetime.now(timezone.utc)

    def check_in_to_rotate(self) -> None:
        if self.status != SecretStatus.CHECKED_OUT:
            raise ValueError(f"Cannot check-in from {self.status.value} state.")
        self.status = SecretStatus.ROTATING
        self.updated_at = datetime.now(timezone.utc)


    def begin_rotation(self) -> None:
        if self.status == SecretStatus.ROTATING:
            raise ValueError("Secret is already in ROTATING state.")
        if self.status != SecretStatus.ACTIVE:
            raise ValueError(f"Cannot begin rotation from {self.status.value} state.")
        self.status = SecretStatus.ROTATING
        self.updated_at = datetime.now(timezone.utc)


    def complete_rotation(self, version: SecretVersion) -> None:
        if self.status != SecretStatus.ROTATING:
            raise ValueError(f"Cannot complete rotation from {self.status.value} state.")
        self.add_version(version)
        self.status = SecretStatus.ACTIVE
        self.updated_at = datetime.now(timezone.utc)


    def fail_rotation(self) -> None:
        if self.status != SecretStatus.ROTATING:
            raise ValueError(f"Cannot fail rotation from {self.status.value} state.")
        self.status = SecretStatus.DESYNCED
        self.updated_at = datetime.now(timezone.utc)


    def restore_from_desynced(self) -> None:
        if self.status != SecretStatus.DESYNCED:
            raise ValueError(f"Cannot restore from {self.status.value} state.")
        self.status = SecretStatus.ACTIVE
        self.updated_at = datetime.now(timezone.utc)


    def disable(self) -> None:
        if self.status == SecretStatus.TOMBSTONED:
            raise ValueError("Cannot disable a tombstoned secret.")
        self.status = SecretStatus.DISABLED
        self.updated_at = datetime.now(timezone.utc)


    def tombstone(self) -> None:
        if self.status == SecretStatus.TOMBSTONED:
            raise ValueError("Secret is already tombstoned.")
        self.status = SecretStatus.TOMBSTONED
        self.updated_at = datetime.now(timezone.utc)


    def get_current_version(self) -> Optional[SecretVersion]:
        if not self.current_version_id:
            return None
        for v in self.versions:
            if v.id == self.current_version_id:
                return v
        return None


class SecretFactory:
    """Constructs Secret aggregates without side effects."""

    @staticmethod
    def create_new_secret(resource_id: UUID) -> Secret:
        now = datetime.now(timezone.utc)
        return Secret(
            id=uuid4(),
            resource_id=resource_id,
            status=SecretStatus.ACTIVE,
            current_version_id=None,
            row_version=1,
            created_at=now,
            updated_at=now,
            versions=[]
        )


class SecretDomainService:
    """Enforces domain invariants across aggregates."""

    @staticmethod
    def ensure_can_rotate(secret: Secret) -> None:
        if secret.status in (SecretStatus.DISABLED, SecretStatus.TOMBSTONED):
            raise ValueError(f"Cannot rotate a secret in {secret.status.value} state.")
