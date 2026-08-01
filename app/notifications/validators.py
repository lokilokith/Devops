from datetime import datetime
from uuid import UUID

from werkzeug.exceptions import BadRequest

from app.notifications.models import (
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)


def validate_filter_params(args: dict) -> dict:
    parsed = {}

    if args.get("status"):
        try:
            parsed["status"] = NotificationStatus(args["status"])
        except ValueError:
            raise BadRequest(
                f"Invalid status. Must be one of {[e.value for e in NotificationStatus]}"
            )

    if args.get("type"):
        try:
            parsed["type_"] = NotificationType(args["type"])
        except ValueError:
            raise BadRequest(
                f"Invalid type. Must be one of {[e.value for e in NotificationType]}"
            )

    if args.get("priority"):
        try:
            parsed["priority"] = NotificationPriority(args["priority"])
        except ValueError:
            raise BadRequest(
                f"Invalid priority. Must be one of {[e.value for e in NotificationPriority]}"
            )

    if args.get("is_read") is not None:
        val = args["is_read"].lower()
        if val in ["true", "1", "yes"]:
            parsed["is_read"] = True
        elif val in ["false", "0", "no"]:
            parsed["is_read"] = False
        else:
            raise BadRequest("Invalid is_read. Must be true/false.")

    if args.get("recipient"):
        try:
            parsed["recipient_id"] = UUID(args["recipient"])
        except ValueError:
            raise BadRequest("Invalid recipient UUID format.")

    if args.get("created_after"):
        try:
            parsed["created_after"] = datetime.fromisoformat(
                args["created_after"].replace("Z", "+00:00")
            )
        except ValueError:
            raise BadRequest("Invalid created_after date format (ISO 8601 expected).")

    if args.get("created_before"):
        try:
            parsed["created_before"] = datetime.fromisoformat(
                args["created_before"].replace("Z", "+00:00")
            )
        except ValueError:
            raise BadRequest("Invalid created_before date format (ISO 8601 expected).")

    limit = args.get("limit")
    if limit is not None:
        try:
            limit = int(limit)
            if limit < 1 or limit > 1000:
                raise ValueError()
            parsed["limit"] = limit
        except ValueError:
            raise BadRequest("Limit must be an integer between 1 and 1000.")

    offset = args.get("offset")
    if offset is not None:
        try:
            offset = int(offset)
            if offset < 0:
                raise ValueError()
            parsed["offset"] = offset
        except ValueError:
            raise BadRequest("Offset must be a non-negative integer.")

    return parsed
