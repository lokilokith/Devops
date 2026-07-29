"""Identity Validation Logic."""
import re
from uuid import UUID
from werkzeug.exceptions import UnprocessableEntity

def validate_uuid(val: str) -> UUID:
    try:
        return UUID(val)
    except ValueError:
        raise UnprocessableEntity(f"Invalid UUID format: {val}")

def validate_email(email: str):
    if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        raise UnprocessableEntity("Invalid email format")

def validate_username(username: str):
    if not username or len(username) < 3:
        raise UnprocessableEntity("Username must be at least 3 characters long")
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise UnprocessableEntity("Username contains invalid characters")

def validate_employee_id(emp_id: str):
    if not emp_id:
        raise UnprocessableEntity("Employee ID is required")

def validate_password(password: str):
    if not password or len(password) < 8:
        raise UnprocessableEntity("Password must be at least 8 characters long")

def validate_user_create(data: dict):
    required = ["employee_id", "username", "email", "full_name", "password"]
    for req in required:
        if req not in data:
            raise UnprocessableEntity(f"Missing required field: {req}")
    
    validate_employee_id(data["employee_id"])
    validate_username(data["username"])
    validate_email(data["email"])
    validate_password(data["password"])
    
    if "manager_user_id" in data and data["manager_user_id"]:
        validate_uuid(data["manager_user_id"])

def validate_user_update(data: dict):
    if "full_name" not in data or not data["full_name"]:
        raise UnprocessableEntity("Missing required field: full_name")
    if "status" not in data or not data["status"]:
        raise UnprocessableEntity("Missing required field: status")

def validate_user_patch(data: dict):
    # Just ensure it's a dict and maybe validate fields if present
    pass
