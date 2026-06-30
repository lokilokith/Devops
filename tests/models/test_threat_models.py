"""OpsForge Model Unit Tests.

Validates Threat model serialization, defaults, and model schemas.
"""

from datetime import datetime, timezone
from app.models.threat import Threat
from app.extensions import db


def test_threat_model_creation_and_defaults(app):
    """Verifies that a threat model can be successfully created with correct defaults."""
    threat = Threat(
        indicator="192.168.1.1",
        indicator_type="ip",
        threat_level="high",
        confidence=85,
        source="Firewall Logs",
        tags=["malicious", "internal"],
    )
    db.session.add(threat)
    db.session.commit()

    assert threat.id is not None
    assert threat.status == "Open"  # Default status
    assert threat.tags == ["malicious", "internal"]
    assert isinstance(threat.created_at, datetime)
    assert isinstance(threat.updated_at, datetime)


def test_threat_model_to_dict(app):
    """Verifies threat serialization to_dict returns correct schema mappings."""
    threat = Threat(
        indicator="example.com",
        indicator_type="domain",
        threat_level="critical",
        confidence=95,
        mitre_attack="T1059",
        source="OSINT",
        analyst_notes="Suspicious registrar",
        assigned_analyst="analyst_alice",
        last_updated_by="analyst_alice",
        status="Investigating",
        tags=["phishing"],
        first_seen=datetime(2026, 6, 30, 9, 0, 0, tzinfo=timezone.utc),
        last_seen=datetime(2026, 6, 30, 10, 0, 0, tzinfo=timezone.utc),
    )
    db.session.add(threat)
    db.session.commit()

    threat_dict = threat.to_dict()

    assert threat_dict["id"] == threat.id
    assert threat_dict["indicator"] == "example.com"
    assert threat_dict["indicator_type"] == "domain"
    assert threat_dict["threat_level"] == "critical"
    assert threat_dict["confidence"] == 95
    assert threat_dict["mitre_attack"] == "T1059"
    assert threat_dict["source"] == "OSINT"
    assert threat_dict["analyst_notes"] == "Suspicious registrar"
    assert threat_dict["assigned_analyst"] == "analyst_alice"
    assert threat_dict["last_updated_by"] == "analyst_alice"
    assert threat_dict["status"] == "Investigating"
    assert threat_dict["tags"] == ["phishing"]
    assert threat_dict["first_seen"] == "2026-06-30T09:00:00+00:00"
    assert threat_dict["last_seen"] == "2026-06-30T10:00:00+00:00"
    assert "created_at" in threat_dict
    assert "updated_at" in threat_dict
