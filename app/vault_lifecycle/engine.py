"""Rotation Eligibility Engine."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from app.vault_lifecycle.models import RotationStatus, SecretRotationPolicy


class RotationEligibilityStatus(str, enum.Enum):
    NOT_DUE = "NOT_DUE"
    DUE = "DUE"
    DISABLED = "DISABLED"
    PAUSED = "PAUSED"
    NO_POLICY = "NO_POLICY"
    INVALID = "INVALID"
    ERROR = "ERROR"


class RotationEligibilityEngine:
    """Evaluates secret rotation policies deterministically."""

    @staticmethod
    def evaluate(policy: SecretRotationPolicy | None) -> dict[str, Any]:
        """
        Evaluate a rotation policy to determine if rotation is required.
        Returns a structured decision.
        """
        now = datetime.now(timezone.utc)

        if not policy:
            return {
                "status": RotationEligibilityStatus.NO_POLICY,
                "reason": "No rotation policy exists",
                "next_rotation_at": None,
            }

        if policy.status == RotationStatus.ERROR:
            return {
                "status": RotationEligibilityStatus.ERROR,
                "reason": "Policy is in ERROR state",
                "next_rotation_at": policy.next_rotation_at,
            }

        if policy.status == RotationStatus.PAUSED:
            return {
                "status": RotationEligibilityStatus.PAUSED,
                "reason": "Policy is PAUSED",
                "next_rotation_at": policy.next_rotation_at,
            }

        if policy.rotation_interval_seconds <= 0:
            return {
                "status": RotationEligibilityStatus.INVALID,
                "reason": "Rotation interval must be positive",
                "next_rotation_at": None,
            }

        if not policy.next_rotation_at:
            # Policy is active, but next_rotation_at is null. Maybe it was never rotated and needs immediate rotation.
            return {
                "status": RotationEligibilityStatus.DUE,
                "reason": "No next rotation scheduled, rotation is due",
                "next_rotation_at": None,
            }

        # Ensure next_rotation_at has timezone
        next_rotation_at = policy.next_rotation_at
        if next_rotation_at.tzinfo is None:
            # If naive, assume UTC
            next_rotation_at = next_rotation_at.replace(tzinfo=timezone.utc)

        if now >= next_rotation_at:
            return {
                "status": RotationEligibilityStatus.DUE,
                "reason": "Next rotation time has been reached or exceeded",
                "next_rotation_at": next_rotation_at,
            }

        return {
            "status": RotationEligibilityStatus.NOT_DUE,
            "reason": "Rotation is not yet due",
            "next_rotation_at": next_rotation_at,
        }
