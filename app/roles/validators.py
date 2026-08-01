"""Roles Validation Logic."""
import re
from uuid import UUID
from werkzeug.exceptions import UnprocessableEntity

def validate_uuid(val: str) -> UUID:
    try:
        return UUID(val)
    except ValueError:
        raise UnprocessableEntity(f"Invalid UUID format: {val}")

def validate_role_code(role_code: str):
    if not role_code or len(role_code) < 3:
        raise UnprocessableEntity("Role code must be at least 3 characters long")
    if not re.match(r"^[A-Z0-9_]+$", role_code):
        raise UnprocessableEntity("Role code must contain only uppercase letters, numbers, and underscores")

def validate_role_name(role_name: str):
    if not role_name or len(role_name) < 3:
        raise UnprocessableEntity("Role name must be at least 3 characters long")

def validate_role_create(data: dict):
    required = ["role_code", "role_name"]
    for req in required:
        if req not in data:
            raise UnprocessableEntity(f"Missing required field: {req}")
    
    validate_role_code(data["role_code"])
    validate_role_name(data["role_name"])

def validate_role_update(data: dict):
    if "role_name" not in data or not data["role_name"]:
        raise UnprocessableEntity("Missing required field: role_name")
    if "status" not in data or not data["status"]:
        raise UnprocessableEntity("Missing required field: status")
    
    validate_role_name(data["role_name"])

def validate_role_patch(data: dict):
    if "role_name" in data and data["role_name"]:
        validate_role_name(data["role_name"])

