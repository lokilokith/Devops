"""Policy Engine Validation Logic."""

import ipaddress
import re
from uuid import UUID

from werkzeug.exceptions import UnprocessableEntity

from app.policy_engine.models import PolicyEffect


def validate_uuid(val: str) -> UUID:
    try:
        return UUID(val)
    except ValueError:
        raise UnprocessableEntity(f"Invalid UUID format: {val}")


def validate_time_format(time_str: str) -> bool:
    """Validate time string is in HH:MM format."""
    return bool(re.match(r"^([01][0-9]|2[0-3]):[0-5][0-9]$", time_str))


def validate_conditions(conditions: dict) -> None:
    """Validate the ABAC JSON conditions schema."""
    if not isinstance(conditions, dict):
        raise UnprocessableEntity("Conditions must be a JSON object")

    # Validate IP ranges
    if "allowed_ip_ranges" in conditions:
        ranges = conditions["allowed_ip_ranges"]
        if not isinstance(ranges, list):
            raise UnprocessableEntity("allowed_ip_ranges must be a list of CIDRs")
        for cidr in ranges:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError:
                raise UnprocessableEntity(f"Invalid CIDR in allowed_ip_ranges: {cidr}")

    # Validate Time restrictions
    if "allowed_hours" in conditions:
        hours = conditions["allowed_hours"]
        if not isinstance(hours, dict) or "start" not in hours or "end" not in hours:
            raise UnprocessableEntity(
                "allowed_hours must be an object with 'start' and 'end' keys"
            )
        if not validate_time_format(hours["start"]):
            raise UnprocessableEntity(
                f"Invalid start time format (use HH:MM): {hours['start']}"
            )
        if not validate_time_format(hours["end"]):
            raise UnprocessableEntity(
                f"Invalid end time format (use HH:MM): {hours['end']}"
            )

    # Validate roles
    if "allowed_roles" in conditions:
        roles = conditions["allowed_roles"]
        if not isinstance(roles, list):
            raise UnprocessableEntity("allowed_roles must be a list of role strings")

    # Resource Attributes
    if "environment" in conditions:
        if not isinstance(conditions["environment"], str):
            raise UnprocessableEntity("environment condition must be a string")


def validate_policy_create(data: dict) -> None:
    required = ["name", "conditions"]
    for req in required:
        if req not in data:
            raise UnprocessableEntity(f"Missing required field: {req}")

    if not data["name"] or len(data["name"]) < 3:
        raise UnprocessableEntity("Policy name must be at least 3 characters long")

    if "effect" in data:
        try:
            PolicyEffect(data["effect"].lower())
        except ValueError:
            raise UnprocessableEntity(
                f"Invalid effect. Must be one of: {[e.value for e in PolicyEffect]}"
            )

    validate_conditions(data["conditions"])


def validate_policy_update(data: dict) -> None:
    if "conditions" in data:
        validate_conditions(data["conditions"])
    if "effect" in data:
        try:
            PolicyEffect(data["effect"].lower())
        except ValueError:
            raise UnprocessableEntity(
                f"Invalid effect. Must be one of: {[e.value for e in PolicyEffect]}"
            )
