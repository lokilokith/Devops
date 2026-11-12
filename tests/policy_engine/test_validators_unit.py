"""Unit tests for Policy Engine validators."""

import pytest
from werkzeug.exceptions import UnprocessableEntity

from app.policy_engine.validators import (
    validate_conditions,
    validate_policy_create,
    validate_policy_update,
    validate_time_format,
    validate_uuid,
)


def test_validate_uuid_success_and_failure():
    valid_uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    u = validate_uuid(valid_uuid_str)
    assert str(u) == valid_uuid_str

    with pytest.raises(UnprocessableEntity, match="Invalid UUID format"):
        validate_uuid("not-a-uuid")


def test_validate_time_format():
    assert validate_time_format("09:00") is True
    assert validate_time_format("23:59") is True
    assert validate_time_format("24:00") is False
    assert validate_time_format("9:00") is False
    assert validate_time_format("invalid") is False


def test_validate_conditions():
    # Valid conditions
    validate_conditions(
        {
            "allowed_ip_ranges": ["192.168.1.0/24", "10.0.0.1/32"],
            "allowed_hours": {"start": "08:00", "end": "17:00"},
            "allowed_roles": ["admin", "dev"],
            "environment": "production",
        }
    )

    # Non-dict conditions
    with pytest.raises(UnprocessableEntity, match="Conditions must be a JSON object"):
        validate_conditions(["not", "dict"])

    # Invalid CIDRs
    with pytest.raises(UnprocessableEntity, match="allowed_ip_ranges must be a list"):
        validate_conditions({"allowed_ip_ranges": "192.168.1.1/32"})

    with pytest.raises(UnprocessableEntity, match="Invalid CIDR in allowed_ip_ranges"):
        validate_conditions({"allowed_ip_ranges": ["not-a-cidr"]})

    # Invalid hours
    with pytest.raises(UnprocessableEntity, match="allowed_hours must be an object"):
        validate_conditions({"allowed_hours": "08:00-17:00"})

    with pytest.raises(UnprocessableEntity, match="Invalid start time format"):
        validate_conditions({"allowed_hours": {"start": "invalid", "end": "17:00"}})

    with pytest.raises(UnprocessableEntity, match="Invalid end time format"):
        validate_conditions({"allowed_hours": {"start": "08:00", "end": "25:00"}})

    # Invalid roles
    with pytest.raises(UnprocessableEntity, match="allowed_roles must be a list"):
        validate_conditions({"allowed_roles": "admin"})

    # Invalid environment
    with pytest.raises(
        UnprocessableEntity, match="environment condition must be a string"
    ):
        validate_conditions({"environment": 123})


def test_validate_policy_create_and_update():
    # Valid create
    validate_policy_create(
        {
            "name": "Valid Policy",
            "conditions": {},
            "effect": "ALLOW",
        }
    )

    # Missing name
    with pytest.raises(UnprocessableEntity, match="Missing required field: name"):
        validate_policy_create({"conditions": {}})

    # Short name
    with pytest.raises(
        UnprocessableEntity, match="Policy name must be at least 3 characters"
    ):
        validate_policy_create({"name": "ab", "conditions": {}})

    # Invalid effect
    with pytest.raises(UnprocessableEntity, match="Invalid effect"):
        validate_policy_create(
            {"name": "Valid Name", "conditions": {}, "effect": "INVALID"}
        )

    # Valid update
    validate_policy_update({"conditions": {"environment": "staging"}, "effect": "DENY"})

    # Invalid effect update
    with pytest.raises(UnprocessableEntity, match="Invalid effect"):
        validate_policy_update({"effect": "UNKNOWN"})
