"""Policy Engine domain models for OpsForge."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import JSON, Boolean, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import BaseModel


class PolicyEffect(str, enum.Enum):
    """Effect of the policy rule."""

    ALLOW = "allow"
    DENY = "deny"


class AccessPolicy(BaseModel):
    """ABAC policy storage."""

    __tablename__ = "access_policies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    max_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effect: Mapped[PolicyEffect] = mapped_column(
        Enum(
            PolicyEffect,
            name="policy_effect_enum",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PolicyEffect.ALLOW,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

__all__ = ["AccessPolicy", "PolicyEffect"]
