"""OpsForge Threat Service Tests.

Verifies service CRUD, input validation, state machine transitions, and transaction rollback operations.
"""

import pytest
from unittest.mock import patch
from app.services.threat_service import ThreatService
from app.utils.exceptions import (
    ValidationException,
    ThreatNotFoundException,
    InvalidStatusTransition,
    DatabaseOperationException,
)


def test_create_threat_validation(app):
    """Verifies that create_threat raises ValidationException on invalid properties."""
    # Test confidence out of bounds
    with pytest.raises(ValidationException) as exc:
        ThreatService.create_threat(
            {
                "indicator": "1.1.1.1",
                "indicator_type": "ip",
                "threat_level": "low",
                "confidence": 150,  # Invalid confidence
                "source": "intel",
            }
        )
    assert "Confidence" in str(exc.value)

    # Test invalid indicator_type
    with pytest.raises(ValidationException) as exc:
        ThreatService.create_threat(
            {
                "indicator": "1.1.1.1",
                "indicator_type": "invalid_type",
                "threat_level": "low",
                "confidence": 50,
                "source": "intel",
            }
        )
    assert "Indicator type" in str(exc.value)

    # Test missing required field
    with pytest.raises(ValidationException) as exc:
        ThreatService.create_threat(
            {
                "indicator": "1.1.1.1",
                "indicator_type": "ip",
                "threat_level": "low",
                "confidence": 50,
                # missing source
            }
        )
    assert "Required field" in str(exc.value)


def test_threat_status_state_machine(app, db_session):
    """Verifies that status transitions adhere to status state machine paths."""
    threat = ThreatService.create_threat(
        {
            "indicator": "1.1.1.1",
            "indicator_type": "ip",
            "threat_level": "low",
            "confidence": 50,
            "source": "intel",
        }
    )
    assert threat.status == "Open"

    # Open -> Investigating (Allowed)
    ThreatService.change_status(threat.id, "Investigating", "analyst_bob")
    assert threat.status == "Investigating"
    assert threat.assigned_analyst == "analyst_bob"

    # Investigating -> Closed (Illegal, must go through Contained or False Positive)
    with pytest.raises(InvalidStatusTransition):
        ThreatService.change_status(threat.id, "Closed", "analyst_bob")

    # Investigating -> Contained (Allowed)
    ThreatService.change_status(threat.id, "Contained", "analyst_bob")
    assert threat.status == "Contained"

    # Contained -> Closed (Allowed)
    ThreatService.change_status(threat.id, "Closed", "analyst_bob")
    assert threat.status == "Closed"

    # Closed -> Open (Illegal)
    with pytest.raises(InvalidStatusTransition):
        ThreatService.change_status(threat.id, "Open", "analyst_bob")


def test_get_threat_by_id_missing_raises_exception(app):
    """Verifies get_threat raises ThreatNotFoundException if ID doesn't exist."""
    with pytest.raises(ThreatNotFoundException):
        ThreatService.get_threat(9999)


def test_get_stats_calculation(app, db_session):
    """Verifies that stats compile aggregation tallies accurately."""
    ThreatService.create_threat(
        {
            "indicator": "1.1.1.1",
            "indicator_type": "ip",
            "threat_level": "critical",
            "confidence": 90,
            "source": "intel",
        }
    )
    ThreatService.create_threat(
        {
            "indicator": "2.2.2.2",
            "indicator_type": "ip",
            "threat_level": "high",
            "confidence": 80,
            "source": "intel",
        }
    )

    stats = ThreatService.get_statistics()
    assert stats["total"] == 2
    assert stats["critical"] == 1
    assert stats["high"] == 1
    assert stats["open"] == 2
    assert stats["closed"] == 0
    assert stats["indicator_types"]["ip"] == 2


def test_transactional_rollback_on_database_error(app, db_session):
    """Verifies that database failures trigger rollback operations in the service layer."""
    threat_data = {
        "indicator": "1.1.1.1",
        "indicator_type": "ip",
        "threat_level": "low",
        "confidence": 50,
        "source": "intel",
    }

    with patch(
        "app.extensions.db.session.commit",
        side_effect=Exception("Database connection failure"),
    ):
        with patch("app.extensions.db.session.rollback") as mock_rollback:
            with pytest.raises(DatabaseOperationException):
                ThreatService.create_threat(threat_data)

            mock_rollback.assert_called_once()
