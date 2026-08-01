"""RolePermissions Validation Logic."""

from uuid import UUID

from werkzeug.exceptions import UnprocessableEntity


def validate_uuid(val: str) -> UUID:
    try:
        return UUID(val)
    except ValueError:
        raise UnprocessableEntity(f"Invalid UUID format: {val}")


def validate_permission_assignment(data: dict):
    if "permission_id" not in data:
        raise UnprocessableEntity("Missing required field: permission_id")
    return validate_uuid(data["permission_id"])
