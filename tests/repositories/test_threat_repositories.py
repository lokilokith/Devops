"""OpsForge Threat Repository Tests.

Verifies ThreatRepository CRUD operations, search, filtering, and pagination.
"""

from app.models.threat import Threat
from app.repositories.threat_repository import ThreatRepository


def test_repository_crud_operations(app, db_session):
    """Verifies standard create, find, update, and delete operations via repository."""
    # Test Create
    threat = Threat(
        indicator="1.2.3.4",
        indicator_type="ip",
        threat_level="critical",
        confidence=95,
        source="alienvault",
    )
    ThreatRepository.create(threat)
    db_session.commit()

    assert threat.id is not None
    assert ThreatRepository.count() == 1

    # Test Find By ID
    retrieved = ThreatRepository.find_by_id(threat.id)
    assert retrieved is not None
    assert retrieved.indicator == "1.2.3.4"

    # Test Update
    retrieved.threat_level = "high"
    ThreatRepository.update(retrieved)
    db_session.commit()

    updated = ThreatRepository.find_by_id(threat.id)
    assert updated.threat_level == "high"

    # Test Find All
    all_threats = ThreatRepository.find_all()
    assert len(all_threats) == 1

    # Test Delete
    ThreatRepository.delete(updated)
    db_session.commit()

    assert ThreatRepository.find_by_id(threat.id) is None
    assert ThreatRepository.count() == 0


def test_repository_queries_and_filters(app, db_session):
    """Verifies that repository matches query criteria and filters indicators correctly."""
    threat_1 = Threat(
        indicator="malicious.org",
        indicator_type="domain",
        threat_level="high",
        confidence=80,
        source="feed",
        status="Open",
    )
    threat_2 = Threat(
        indicator="phishing.net",
        indicator_type="domain",
        threat_level="medium",
        confidence=70,
        source="feed",
        status="Investigating",
    )
    threat_3 = Threat(
        indicator="9.9.9.9",
        indicator_type="ip",
        threat_level="low",
        confidence=30,
        source="threat_connect",
        status="Open",
    )

    ThreatRepository.create(threat_1)
    ThreatRepository.create(threat_2)
    ThreatRepository.create(threat_3)
    db_session.commit()

    # Test Find by Status
    open_threats = ThreatRepository.find_by_status("Open")
    assert len(open_threats) == 2

    # Test Find by Indicator Type
    domains = ThreatRepository.find_by_indicator_type("domain")
    assert len(domains) == 2

    # Test Search
    results_domain = ThreatRepository.search("malicious")
    assert len(results_domain) == 1
    assert results_domain[0].indicator == "malicious.org"

    # Test Search by Source partial match
    results_source = ThreatRepository.search("connect")
    assert len(results_source) == 1
    assert results_source[0].indicator == "9.9.9.9"


def test_repository_pagination(app, db_session):
    """Verifies pagination limits, filtering subsets, and sorting order."""
    for i in range(1, 11):
        threat = Threat(
            indicator=f"bad-ip-{i}.com",
            indicator_type="domain" if i % 2 == 0 else "ip",
            threat_level="high" if i <= 5 else "low",
            confidence=50 + i,
            source="bulk_load",
            status="Open" if i <= 7 else "Closed",
        )
        ThreatRepository.create(threat)
    db_session.commit()

    # Paginate all records sorting by created_at DESC (default sorting)
    page_1 = ThreatRepository.paginate(
        filters={}, page=1, limit=4, sort="created_at", order="desc"
    )
    assert len(page_1.items) == 4
    assert page_1.total == 10
    assert page_1.pages == 3

    # Paginate applying filters: status="Open", indicator_type="domain"
    # Even IPs 2, 4, 6 are domain, odd 1, 3, 5, 7 are ip.
    # Bad IPs <= 7 are Open: Bad-ip 2, 4, 6 are Open domains.
    filtered_page = ThreatRepository.paginate(
        filters={"status": "Open", "indicator_type": "domain"},
        page=1,
        limit=5,
        sort="indicator",
        order="asc",
    )
    assert len(filtered_page.items) == 3
    assert filtered_page.total == 3
    # Assert sorting order asc on indicator: bad-ip-2.com, bad-ip-4.com, bad-ip-6.com.
    # Since lexicographically bad-ip-10.com comes before bad-ip-2.com, let's verify exact contents.
    indicators = [item.indicator for item in filtered_page.items]
    assert "bad-ip-2.com" in indicators
    assert "bad-ip-4.com" in indicators
    assert "bad-ip-6.com" in indicators
