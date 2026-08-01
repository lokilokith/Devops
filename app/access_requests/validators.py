"""AccessRequest Validation Logic."""

from uuid import UUID
from datetime import datetime, timezone
from werkzeug.exceptions import UnprocessableEntity

from app.access_requests.models import AccessRequestPriority


def validate_uuid(val: str) -> UUID:
    try:
        return UUID(val)
    except ValueError:
        raise UnprocessableEntity(f"Invalid UUID format: {val}")


def validate_access_request_create(data: dict):
    if "business_justification" not in data or not data["business_justification"]:
        raise UnprocessableEntity("Missing required field: business_justification")

    if len(data["business_justification"]) < 10:
        raise UnprocessableEntity(
            "business_justification must be at least 10 characters long"
        )

    has_role = "requested_role_id" in data and data["requested_role_id"]
    has_resource = "requested_resource_id" in data and data["requested_resource_id"]

    if not has_role and not has_resource:
        raise UnprocessableEntity(
            "Must specify either requested_role_id or requested_resource_id."
        )

    if has_role and has_resource:
        raise UnprocessableEntity(
            "Cannot specify both requested_role_id and requested_resource_id."
        )

    if has_role:
        validate_uuid(data["requested_role_id"])
    if has_resource:
        validate_uuid(data["requested_resource_id"])

    if "priority" in data:
        try:
            AccessRequestPriority(data["priority"])
        except ValueError:
            raise UnprocessableEntity("Invalid priority value.")

    if (
        "requested_start" in data
        and data["requested_start"]
        and "requested_end" in data
        and data["requested_end"]
    ):
        try:
            start = datetime.fromisoformat(
                data["requested_start"].replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(data["requested_end"].replace("Z", "+00:00"))
            if start >= end:
                raise UnprocessableEntity(
                    "requested_start must be before requested_end."
                )
        except ValueError:
            raise UnprocessableEntity("Invalid datetime format.")
