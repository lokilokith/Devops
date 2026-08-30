"""Vault SQLAlchemy Models."""

from __future__ import annotations

import enum
from typing import Any, List
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel
from app.vault.domain import SecretStatus


class KMSProviderType(str, enum.Enum):
    LOCAL = "local"
    AWS_KMS = "aws_kms"
    AZURE_KV = "azure_kv"
    HASHICORP = "hashicorp"


class KMSConfiguration(BaseModel):
    __tablename__ = "kms_configurations"

    __table_args__ = (
        # Ensure only one KMS configuration can be active at a time
        Index(
            "ix_active_kms",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    provider_type: Mapped[KMSProviderType] = mapped_column(
        Enum(
            KMSProviderType,
            name="kms_provider_type_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    kms_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    kms_key_id: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VaultSecret(BaseModel):
    """SQLAlchemy model for Secret Aggregate Root."""

    __tablename__ = "vault_secrets"

    resource_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[SecretStatus] = mapped_column(
        Enum(
            SecretStatus,
            name="secret_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=SecretStatus.ACTIVE,
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    current_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "vault_secret_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_vault_secrets_current_version_id",
        ),
        nullable=True,
    )

    versions: Mapped[List["VaultSecretVersion"]] = relationship(
        "VaultSecretVersion",
        primaryjoin="VaultSecret.id == VaultSecretVersion.secret_id",
        cascade="all, delete-orphan",
        order_by="VaultSecretVersion.created_at",
    )


class VaultSecretVersion(BaseModel):
    """SQLAlchemy model for SecretVersion entity."""

    __tablename__ = "vault_secret_versions"

    secret_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vault_secrets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    encrypted_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Metadata mapped fields
    key_version: Mapped[str] = mapped_column(String(50), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(50), nullable=False)
    nonce: Mapped[str] = mapped_column(String(100), nullable=False)
    encryption_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


__all__ = ["VaultSecret", "VaultSecretVersion"]
