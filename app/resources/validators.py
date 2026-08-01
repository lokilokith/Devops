"""Resources Validation Logic."""
import re
from uuid import UUID
from werkzeug.exceptions import UnprocessableEntity

def validate_uuid(val: str) -> UUID:
    try:
        return UUID(val)
    except ValueError:
        raise UnprocessableEntity(f"Invalid UUID format: {val}")

def validate_resource_code(resource_code: str):
    if not resource_code or len(resource_code) < 3:
        raise UnprocessableEntity("Resource code must be at least 3 characters long")
    if not re.match(r"^[A-Z0-9_]+$", resource_code):
        raise UnprocessableEntity("Resource code must contain only uppercase letters, numbers, and underscores")

def validate_resource_name(resource_name: str):
    if not resource_name or len(resource_name) < 3:
        raise UnprocessableEntity("Resource name must be at least 3 characters long")

def validate_resource_create(data: dict):
    required = ["resource_code", "resource_name"]
    for req in required:
        if req not in data:
            raise UnprocessableEntity(f"Missing required field: {req}")
    
    validate_resource_code(data["resource_code"])
    validate_resource_name(data["resource_name"])

def validate_resource_update(data: dict):
    if "resource_name" not in data or not data["resource_name"]:
        raise UnprocessableEntity("Missing required field: resource_name")
    if "resource_type" not in data or not data["resource_type"]:
        raise UnprocessableEntity("Missing required field: resource_type")
    if "status" not in data or not data["status"]:
        raise UnprocessableEntity("Missing required field: status")
    
    validate_resource_name(data["resource_name"])

def validate_resource_patch(data: dict):
    if "resource_name" in data and data["resource_name"]:
        validate_resource_name(data["resource_name"])

