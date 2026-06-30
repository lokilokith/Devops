"""OpsForge Repository Unit Tests.

Validates ThreatRepository persistence operations.
"""

from app.models.threat import Threat
from app.services.threat_repository import ThreatRepository
from app.extensions import db


def test_threat_repository_crud_operations(app):
    """Verifies basic create, find, update, and delete repository methods."""
    # 1. Create
    threat = Threat(
        indicator="malicious-payload-hash",
        indicator_type="hash",
        threat_level="medium",
        confidence=60,
        source="ThreatFeed",
    )
    ThreatRepository.create(threat)
    db.session.commit()

    assert threat.id is not None

    # 2. Find by ID
    found = ThreatRepository.find_by_id(threat.id)
    assert found is not None
    assert found.indicator == "malicious-payload-hash"

    # 3. Find by Indicator
    indicator_matches = ThreatRepository.find_by_indicator("malicious-payload-hash")
    assert len(indicator_matches) == 1
    assert indicator_matches[0].id == threat.id

    # 4. Find by Status
    status_matches = ThreatRepository.find_by_status("Open")
    assert len(status_matches) == 1
    assert status_matches[0].id == threat.id

    # 5. Update
    threat.confidence = 75
    ThreatRepository.update(threat)
    db.session.commit()
    assert ThreatRepository.find_by_id(threat.id).confidence == 75

    # 6. Delete
    ThreatRepository.delete(threat)
    db.session.commit()
    assert ThreatRepository.find_by_id(threat.id) is None


def test_threat_repository_paginate(app):
    """Verifies that the repository paginate method returns filtered, sorted, and paginated records."""
    # Seed threats
    threat1 = Threat(
        indicator="10.0.0.1",
        indicator_type="ip",
        threat_level="low",
        confidence=10,
        source="feed",
        status="Open",
    )
    threat2 = Threat(
        indicator="10.0.0.2",
        indicator_type="ip",
        threat_level="high",
        confidence=80,
        source="feed",
        status="Investigating",
    )
    threat3 = Threat(
        indicator="evil.com",
        indicator_type="domain",
        threat_level="critical",
        confidence=95,
        source="feed",
        status="Open",
    )

    db.session.add_all([threat1, threat2, threat3])
    db.session.commit()

    # Pagination with filters
    filters = {"status": "Open", "indicator_type": "ip"}
    pagination = ThreatRepository.paginate(
        filters, page=1, limit=10, sort="confidence", order="asc"
    )

    assert pagination.total == 1
    assert pagination.items[0].indicator == "10.0.0.1"

    # Sorting
    pagination_sorted = ThreatRepository.paginate(
        {}, page=1, limit=10, sort="confidence", order="desc"
    )
    assert pagination_sorted.total == 3
    assert pagination_sorted.items[0].indicator == "evil.com"  # 95 confidence
    assert pagination_sorted.items[1].indicator == "10.0.0.2"  # 80 confidence
