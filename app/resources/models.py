"""Resource domain models for OpsForge.

This module defines the Resource entity for the infrastructure/asset domain.
"""

from __future__ import annotations

import enum
from sqlalchemy import CheckConstraint, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

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

    def __repr__(self) -> str:
        return (
            f"<Resource(resource_code={self.resource_code!r}, "
            f"resource_name={self.resource_name!r})>"
        )

__all__ = ["Resource", "ResourceStatus", "ResourceType"]
