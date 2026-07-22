"""OpsForge Input Validators.

Validates indicator properties and values against domain constraints.
"""

from app.constants import INDICATOR_TYPES, THREAT_LEVELS, THREAT_STATUSES
from app.utils.exceptions import ValidationException


def validate_threat_data(data: dict) -> None:
    """Validates core threat properties against domain constraints."""
    # Confidence Check
    confidence = data.get("confidence")
    if confidence is not None:
        try:
            val = int(confidence)
            if val < 0 or val > 100:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValidationException(
                f"Validation Error: Confidence '{confidence}'"
                f" must be an integer between 0 and 100."
            )

    # Indicator Type Check
    ind_type = data.get("indicator_type")
    if ind_type is not None and ind_type not in INDICATOR_TYPES:
        raise ValidationException(
            f"Validation Error: Indicator type '{ind_type}' is invalid. "
            f"Allowed values are: {', '.join(INDICATOR_TYPES)}."
        )

    # Threat Level Check
    threat_lvl = data.get("threat_level")
    if threat_lvl is not None and threat_lvl not in THREAT_LEVELS:
        raise ValidationException(
            f"Validation Error: Threat level '{threat_lvl}' is invalid. "
            f"Allowed values are: {', '.join(THREAT_LEVELS)}."
        )

    # Status Check
    status = data.get("status")
    if status is not None and status not in THREAT_STATUSES:
        raise ValidationException(
            f"Validation Error: Status '{status}' is invalid. "
            f"Allowed values are: {', '.join(THREAT_STATUSES)}."
        )


def validate_create_threat_data(data: dict) -> None:
    """Validate required properties and domain constraints.

    Ensures all mandatory fields are present on creation.
    """
    required_fields = [
        "indicator",
        "indicator_type",
        "threat_level",
        "confidence",
        "source",
    ]
    for field in required_fields:
        if data.get(field) is None:
            raise ValidationException(
                f"Validation Error: Required field '{field}' is missing."
            )

    validate_threat_data(data)

