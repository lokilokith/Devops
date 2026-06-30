"""OpsForge Service Layer Unit Tests.

Validates ThreatService business logic, input validation, and state machine transition rules.
"""

import pytest
from app.services.threat_service import ThreatService
from app.utils.custom_exceptions import ValidationException, ResourceNotFoundException


def test_create_threat_validation(app):
    """Verifies that create_threat enforces field requirements and confidence boundaries."""
    # Test valid creation
    valid_data = {
        "indicator": "192.168.1.50",
        "indicator_type": "ip",
        "threat_level": "medium",
        "confidence": 75,
        "source": "Egress Logs",
    }
    threat = ThreatService.create_threat(valid_data)
    assert threat.id is not None
    assert threat.confidence == 75

    # Test out of bounds confidence
    invalid_data = valid_data.copy()
    invalid_data["confidence"] = 150
    with pytest.raises(ValidationException) as excinfo:
        ThreatService.create_threat(invalid_data)
    assert "confidence" in str(excinfo.value).lower()

    # Test negative confidence
    invalid_data["confidence"] = -5
    with pytest.raises(ValidationException):
        ThreatService.create_threat(invalid_data)

    # Test non-integer confidence
    invalid_data["confidence"] = "very_high"
    with pytest.raises(ValidationException):
        ThreatService.create_threat(invalid_data)

    # Test invalid indicator_type
    invalid_data = valid_data.copy()
    invalid_data["indicator_type"] = "user_agent"
    with pytest.raises(ValidationException):
        ThreatService.create_threat(invalid_data)

    # Test invalid threat_level
    invalid_data = valid_data.copy()
    invalid_data["threat_level"] = "extreme"
    with pytest.raises(ValidationException):
        ThreatService.create_threat(invalid_data)


def test_threat_status_state_machine(app):
    """Verifies that update_threat_status enforces state machine rules."""
    valid_data = {
        "indicator": "http://malicious-site.com/path",
        "indicator_type": "url",
        "threat_level": "low",
        "confidence": 20,
        "source": "Spam Emails",
        "status": "Open",
    }
    threat = ThreatService.create_threat(valid_data)
    assert threat.status == "Open"

    # 1. Allowed: Open -> Investigating
    ThreatService.update_threat_status(threat.id, "Investigating")
    assert threat.status == "Investigating"

    # 2. Allowed: Investigating -> Contained
    ThreatService.update_threat_status(threat.id, "Contained")
    assert threat.status == "Contained"

    # 3. Allowed: Contained -> Closed
    ThreatService.update_threat_status(threat.id, "Closed")
    assert threat.status == "Closed"

    # 4. Blocked: Closed -> Open (Re-opening ticket is blocked)
    with pytest.raises(ValidationException) as excinfo:
        ThreatService.update_threat_status(threat.id, "Open")
    assert "state transition" in str(excinfo.value).lower()
    assert "blocked" in str(excinfo.value).lower()

    # 5. Alternate allowed flow: Open -> False Positive -> Closed
    threat2 = ThreatService.create_threat(valid_data)
    ThreatService.update_threat_status(threat2.id, "False Positive")
    assert threat2.status == "False Positive"
    ThreatService.update_threat_status(threat2.id, "Closed")
    assert threat2.status == "Closed"

    # 6. Blocked: False Positive -> Open
    with pytest.raises(ValidationException):
        ThreatService.update_threat_status(threat2.id, "Open")


def test_get_threat_by_id_missing_raises_exception(app):
    """Verifies that fetching a non-existent threat throws ResourceNotFoundException."""
    with pytest.raises(ResourceNotFoundException):
        ThreatService.get_threat_by_id(9999)


def test_get_stats_calculation(app):
    """Verifies that get_stats returns correct aggregated count tallies."""
    # Seed 3 threats
    ThreatService.create_threat(
        {
            "indicator": "1.1.1.1",
            "indicator_type": "ip",
            "threat_level": "critical",
            "confidence": 100,
            "source": "feed",
            "status": "Open",
        }
    )
    ThreatService.create_threat(
        {
            "indicator": "google.com",
            "indicator_type": "domain",
            "threat_level": "high",
            "confidence": 90,
            "source": "feed",
            "status": "Closed",
        }
    )
    ThreatService.create_threat(
        {
            "indicator": "2.2.2.2",
            "indicator_type": "ip",
            "threat_level": "low",
            "confidence": 15,
            "source": "feed",
            "status": "Open",
        }
    )

    stats = ThreatService.get_stats()
    assert stats["total"] == 3
    assert stats["critical"] == 1
    assert stats["high"] == 1
    assert stats["open"] == 2
    assert stats["closed"] == 1
    assert stats["indicator_types"]["ip"] == 2
    assert stats["indicator_types"]["domain"] == 1
    assert stats["indicator_types"]["hash"] == 0
    assert stats["last_updated"] is not None
