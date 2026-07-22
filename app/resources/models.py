"""Resource domain models for OpsForge.

This module defines the Resource entity for managing protected infrastructure assets.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.shared.database import BaseModel

if TYPE_CHECKING:
    from app.identity.models import User


class ResourceType(str, enum.Enum):
    """Approved logical classification for managed assets."""

    SERVER = "server"
    DATABASE = "database"
    CLOUD_ACCOUNT = "cloud_account"
    KUBERNETES_CLUSTER = "kubernetes_cluster"
    NETWORK_DEVICE = "network_device"
    SAAS_APP = "saas_app"


class ResourceStatus(str, enum.Enum):
    """Approved lifecycle and state configuration for a resource."""

    PLANNED = "planned"
    ACTIVE = "active"
    MAINTENANCE = "maintenance"
    INACTIVE = "inactive"
    RETIRED = "retired"


class Resource(BaseModel):
    """Protected asset or environment within the PAM boundary.

    Resource tracks the authoritative configuration, network location, environment
    classification, ownership, and metadata for a managed target.
    """

    __tablename__ = "resources"

    # Alignment Check: Replicated the exact constraint pattern from the Roles model
    __table_args__ = (
        CheckConstraint(
            "length(resource_code) >= 3",
            name="ck_resource_code_length",
        ),
    )

    # Alignment Check: Added stable technical identifier to match the V1 schema contract
    resource_code: Mapped[str] = mapped_column(
        String(60), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    # Alignment Check: Renamed to avoid shadowing Python built-ins
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
    )
    environment: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
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
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Unidirectional relationship to keep integration isolated and safe for V1
    owner_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[owner_user_id],
    )

    def __repr__(self) -> str:
        return (
            f"<Resource(resource_code={self.resource_code!r}, "
            f"name={self.name!r}, "
            f"resource_type={self.resource_type.value!r})>"
        )


__all__ = [
    "Resource",
    "ResourceStatus",
    "ResourceType",
]

