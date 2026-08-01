"""Permissions Validation Logic."""
import re
from uuid import UUID
from werkzeug.exceptions import UnprocessableEntity

def validate_uuid(val: str) -> UUID:
    try:
        return UUID(val)
    except ValueError:
        raise UnprocessableEntity(f"Invalid UUID format: {val}")

def validate_permission_code(permission_code: str):
    if not permission_code or len(permission_code) < 3:
        raise UnprocessableEntity("Permission code must be at least 3 characters long")
    if not re.match(r"^[A-Z0-9_]+$", permission_code):
        raise UnprocessableEntity("Permission code must contain only uppercase letters, numbers, and underscores")

def validate_permission_name(permission_name: str):
    if not permission_name or len(permission_name) < 3:
        raise UnprocessableEntity("Permission name must be at least 3 characters long")

def validate_permission_create(data: dict):
    required = ["permission_code", "permission_name"]
    for req in required:
        if req not in data:
            raise UnprocessableEntity(f"Missing required field: {req}")
    
    validate_permission_code(data["permission_code"])
    validate_permission_name(data["permission_name"])

def validate_permission_update(data: dict):
    if "permission_name" not in data or not data["permission_name"]:
        raise UnprocessableEntity("Missing required field: permission_name")
    if "action" not in data or not data["action"]:
        raise UnprocessableEntity("Missing required field: action")
    if "status" not in data or not data["status"]:
        raise UnprocessableEntity("Missing required field: status")
    
    validate_permission_name(data["permission_name"])

def validate_permission_patch(data: dict):
    if "permission_name" in data and data["permission_name"]:
        validate_permission_name(data["permission_name"])

