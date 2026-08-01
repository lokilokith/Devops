"""Pagination Utilities."""

from typing import Tuple

from app.shared.exceptions import ValidationException

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def validate_pagination(skip: str | int, limit: str | int) -> Tuple[int, int]:
    """
    Validates and clamps pagination arguments.
    Ensures limit does not exceed MAX_PAGE_SIZE.
    """
    try:
        skip_val = int(skip)
        limit_val = int(limit)
    except (ValueError, TypeError):
        raise ValidationException("Pagination parameters must be integers.")

    if skip_val < 0:
        raise ValidationException("Skip cannot be negative.")

    if limit_val < 1:
        raise ValidationException("Limit must be at least 1.")

    limit_val = min(limit_val, MAX_PAGE_SIZE)
    return skip_val, limit_val
