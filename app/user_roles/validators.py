"""UserRoles Validation Logic."""

from uuid import UUID
from werkzeug.exceptions import UnprocessableEntity


def validate_uuid(val: str) -> UUID:
    try:
        return UUID(val)
    except ValueError:
        raise UnprocessableEntity(f"Invalid UUID format: {val}")


def validate_role_assignment(data: dict):
    if "role_id" not in data:
        raise UnprocessableEntity("Missing required field: role_id")
    return validate_uuid(data["role_id"])
