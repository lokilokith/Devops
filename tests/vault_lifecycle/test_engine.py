"""Tests for Rotation Eligibility Engine."""

from datetime import datetime, timedelta, timezone
import pytest
import uuid

from app.vault_lifecycle.engine import RotationEligibilityEngine, RotationEligibilityStatus
from app.vault_lifecycle.models import SecretRotationPolicy, RotationStatus


def test_evaluate_no_policy():
    result = RotationEligibilityEngine.evaluate(None)
    assert result["status"] == RotationEligibilityStatus.NO_POLICY


def test_evaluate_error_policy():
    policy = SecretRotationPolicy(status=RotationStatus.ERROR)
    result = RotationEligibilityEngine.evaluate(policy)
    assert result["status"] == RotationEligibilityStatus.ERROR


def test_evaluate_paused_policy():
    policy = SecretRotationPolicy(status=RotationStatus.PAUSED)
    result = RotationEligibilityEngine.evaluate(policy)
    assert result["status"] == RotationEligibilityStatus.PAUSED


def test_evaluate_invalid_interval():
    policy = SecretRotationPolicy(status=RotationStatus.ACTIVE, rotation_interval_seconds=0)
    result = RotationEligibilityEngine.evaluate(policy)
    assert result["status"] == RotationEligibilityStatus.INVALID
    
    policy.rotation_interval_seconds = -10
    result = RotationEligibilityEngine.evaluate(policy)
    assert result["status"] == RotationEligibilityStatus.INVALID


def test_evaluate_due_no_next_rotation():
    policy = SecretRotationPolicy(status=RotationStatus.ACTIVE, rotation_interval_seconds=3600, next_rotation_at=None)
    result = RotationEligibilityEngine.evaluate(policy)
    assert result["status"] == RotationEligibilityStatus.DUE


def test_evaluate_due():
    now = datetime.now(timezone.utc)
    policy = SecretRotationPolicy(
        status=RotationStatus.ACTIVE,
        rotation_interval_seconds=3600,
        next_rotation_at=now - timedelta(seconds=1)
    )
    result = RotationEligibilityEngine.evaluate(policy)
    assert result["status"] == RotationEligibilityStatus.DUE


def test_evaluate_not_due():
    now = datetime.now(timezone.utc)
    policy = SecretRotationPolicy(
        status=RotationStatus.ACTIVE,
        rotation_interval_seconds=3600,
        next_rotation_at=now + timedelta(seconds=3600)
    )
    result = RotationEligibilityEngine.evaluate(policy)
    assert result["status"] == RotationEligibilityStatus.NOT_DUE
