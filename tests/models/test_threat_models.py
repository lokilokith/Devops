"""OpsForge Threat Model Tests.

Verifies Threat model creation, default values, enums, timestamps, and serialization.
"""

from datetime import datetime, timezone
from app.models.threat import Threat


def test_threat_model_creation_and_defaults(app):
    """Verifies that Threat instances are instantiated with correct default states."""
    threat = Threat(
        indicator="1.1.1.1",
        indicator_type="ip",
        threat_level="low",
        confidence=50,
        source="intel_feed",
    )

    assert threat.indicator == "1.1.1.1"
    assert threat.indicator_type == "ip"
    assert threat.threat_level == "low"
    assert threat.confidence == 50
    assert threat.source == "intel_feed"
    assert threat.status == "Open"  # Default status
    assert threat.tags is None
    assert threat.mitre_attack is None
    assert threat.assigned_analyst is None
    assert threat.first_seen is None
    assert threat.last_seen is None


def test_threat_model_serialization(app):
    """Verifies the to_dict method maps properties to serializable schemas."""
    threat = Threat(
        id=42,
        indicator="example.com",
        indicator_type="domain",
        threat_level="high",
        confidence=90,
        mitre_attack="T1566",
        source="analyst_report",
        analyst_notes="Suspicious phishing site",
        assigned_analyst="analyst_alice",
        status="Investigating",
        tags=["phishing", "campaign"],
        first_seen=datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 6, 30, 15, 30, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 7, 1, 9, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 1, 9, 30, 0, tzinfo=timezone.utc),
    )

    serialized = threat.to_dict()

    assert serialized["id"] == 42
    assert serialized["indicator"] == "example.com"
    assert serialized["indicator_type"] == "domain"
    assert serialized["threat_level"] == "high"
    assert serialized["confidence"] == 90
    assert serialized["mitre_attack"] == "T1566"
    assert serialized["source"] == "analyst_report"
    assert (
        serialized["analyst_notes"] == "Phishing campaign notes"
        or "Suspicious phishing site" in serialized["analyst_notes"]
    )
    assert serialized["assigned_analyst"] == "analyst_alice"
    assert serialized["status"] == "Investigating"
    assert serialized["tags"] == ["phishing", "campaign"]
    assert serialized["first_seen"] == "2026-06-29T12:00:00+00:00"
    assert serialized["last_seen"] == "2026-06-30T15:30:00+00:00"
    assert serialized["created_at"] == "2026-07-01T09:00:00+00:00"
    assert serialized["updated_at"] == "2026-07-01T09:30:00+00:00"


def test_threat_model_repr(app):
    """Verifies string representation formatting."""
    threat = Threat(id=1, indicator="192.168.1.1", indicator_type="ip")
    assert repr(threat) == "<Threat 1: ip - 192.168.1.1>"
