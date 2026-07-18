"""Shared validation entrypoints."""

from app.utils.validators import validate_create_threat_data, validate_threat_data

__all__ = ["validate_threat_data", "validate_create_threat_data"]
