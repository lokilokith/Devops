"""Resource domain models for OpsForge.

This module defines the Resource entity for the infrastructure/asset domain.
"""

from __future__ import annotations

import enum
from typing import List
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel


class ResourceType(str, enum.Enum):
    """Approved resource classification."""

    APPLICATION = "application"
    DATABASE = "database"
    SERVER = "server"
    NETWORK = "network"
    CLOUD = "cloud"
    STORAGE = "storage"
    API = "api"
    OTHER = "other"


class ConnectionMethod(str, enum.Enum):
    SSH = "ssh"
    RDP = "rdp"
    HTTPS = "https"
    API = "api"
    OTHER = "other"


class Environment(str, enum.Enum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class Criticality(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResourceStatus(str, enum.Enum):
    """Approved lifecycle state for resources."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    RETIRED = "retired"


class Resource(BaseModel):
    """Infrastructure or software asset tracked by OpsForge."""

    __tablename__ = "resources"

    __table_args__ = (
        CheckConstraint(
            "length(resource_code) >= 3",
            name="ck_resource_code_length",
        ),
    )

    resource_code: Mapped[str] = mapped_column(
        String(60), nullable=False, unique=True, index=True
    )
    resource_name: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(
            ResourceType,
            name="resource_type_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=ResourceType.SERVER,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ResourceStatus] = mapped_column(
        Enum(
            ResourceStatus,
            name="resource_status_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
        default=ResourceStatus.ACTIVE,
    )

    # New PAM fields
    hostname_ip: Mapped[str | None] = mapped_column(String(255), nullable=True)
    protocol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    environment: Mapped[Environment] = mapped_column(
        Enum(
            Environment,
            name="environment_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=Environment.PROD,
    )

    criticality: Mapped[Criticality] = mapped_column(
        Enum(
            Criticality,
            name="criticality_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=Criticality.MEDIUM,
    )

    connection_method: Mapped[ConnectionMethod | None] = mapped_column(
        Enum(
            ConnectionMethod,
            name="connection_method_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )

    auth_mechanism: Mapped[str | None] = mapped_column(String(50), nullable=True)

    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    privileged_accounts: Mapped[List["PrivilegedAccount"]] = relationship(
        "PrivilegedAccount", back_populates="resource", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Resource(resource_code={self.resource_code!r}, "
            f"resource_name={self.resource_name!r})>"
        )


class PrivilegedAccount(BaseModel):
    """Target system account mapped to a resource."""

    __tablename__ = "privileged_accounts"

    resource_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    resource: Mapped["Resource"] = relationship(
        "Resource", back_populates="privileged_accounts"
    )


class ResourceAccessPolicy(BaseModel):
    """Policy defining how a Role accesses a Resource."""

    __tablename__ = "resource_access_policies"

    resource_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    allowed_protocol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    allowed_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    max_session_duration: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # in minutes


__all__ = [
    "Resource",
    "ResourceStatus",
    "ResourceType",
    "ConnectionMethod",
    "Environment",
    "Criticality",
    "PrivilegedAccount",
    "ResourceAccessPolicy",
]
