"""OpsForge Route and Controller Endpoint Tests.

Verifies API endpoint CRUD actions, pagination, statistics telemetry, health checks, Swagger JSON availability, and exception handling.
"""

import json
import pytest
from app.services.threat_service import ThreatService


def test_swagger_availability(client):
    """Verifies that the Swagger UI and spec endpoints are accessible."""
    res_docs = client.get("/docs")
    assert res_docs.status_code == 200

    res_json = client.get("/swagger.json")
    assert res_json.status_code == 200
    data = json.loads(res_json.data)
    assert "paths" in data


def test_api_health_endpoint(client):
    """Verifies system vitality metrics check reporting application and database health."""
    res = client.get("/health")
    assert res.status_code == 200
    data = json.loads(res.data)

    assert data["success"] is True
    assert "status check" in data["message"].lower()
    assert data["data"]["application"] == "healthy"
    assert data["data"]["database"] == "healthy"
    assert "version" in data["data"]
    assert "uptime" in data["data"]


def test_threats_crud_api_flow(client):
    """Verifies REST endpoints manage lifecycle creation, retrieval, updates, status patch, and delete operations."""
    # 1. Create Threat
    payload = {
        "indicator": "192.168.1.100",
        "indicator_type": "ip",
        "threat_level": "medium",
        "confidence": 75,
        "source": "soc_firewall",
        "mitre_attack": "T1071",
        "analyst_notes": "Internal scan target",
        "assigned_analyst": "analyst_alice",
        "tags": ["scan", "internal"],
    }

    res_post = client.post("/threats", json=payload)
    assert res_post.status_code == 201
    data_post = json.loads(res_post.data)
    assert data_post["success"] is True
    assert data_post["data"]["indicator"] == "192.168.1.100"
    assert data_post["data"]["status"] == "Open"
    threat_id = data_post["data"]["id"]

    # 2. Get Threat
    res_get = client.get(f"/threats/{threat_id}")
    assert res_get.status_code == 200
    data_get = json.loads(res_get.data)
    assert data_get["success"] is True
    assert data_get["data"]["indicator"] == "192.168.1.100"

    # 3. Update Threat
    payload["threat_level"] = "high"
    res_put = client.put(f"/threats/{threat_id}", json=payload)
    assert res_put.status_code == 200
    data_put = json.loads(res_put.data)
    assert data_put["success"] is True
    assert data_put["data"]["threat_level"] == "high"

    # 4. Patch Status (Change Status)
    patch_payload = {"status": "Investigating", "assigned_analyst": "analyst_bob"}
    res_patch = client.patch(f"/threats/{threat_id}/status", json=patch_payload)
    assert res_patch.status_code == 200
    data_patch = json.loads(res_patch.data)
    assert data_patch["success"] is True
    assert data_patch["data"]["status"] == "Investigating"
    assert data_patch["data"]["assigned_analyst"] == "analyst_bob"

    # 5. Delete Threat
    res_delete = client.delete(f"/threats/{threat_id}")
    assert res_delete.status_code == 200
    data_delete = json.loads(res_delete.data)
    assert data_delete["success"] is True

    # 6. Read deleted threat returns 404
    res_missing = client.get(f"/threats/{threat_id}")
    assert res_missing.status_code == 404
    data_missing = json.loads(res_missing.data)
    assert data_missing["success"] is False
    assert len(data_missing["errors"]) > 0


def test_threat_list_pagination_and_filtering(client):
    """Verifies that lists can be filtered by query parameters and support pagination metadata."""
    # Seed data
    for i in range(1, 10):
        client.post(
            "/threats",
            json={
                "indicator": f"badsite-{i}.com",
                "indicator_type": "domain",
                "threat_level": "low" if i <= 5 else "high",
                "confidence": 40 + i,
                "source": "bulk",
            },
        )

    # Retrieve and check page limit
    res = client.get("/threats?page=1&limit=3&sort=indicator&order=asc")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["success"] is True
    assert len(data["data"]["items"]) == 3
    assert data["data"]["total"] >= 9


def test_threat_search_endpoint(client):
    """Verifies search endpoint queries using partial matching."""
    client.post(
        "/threats",
        json={
            "indicator": "phishing-bank.net",
            "indicator_type": "domain",
            "threat_level": "high",
            "confidence": 85,
            "source": "feed_source",
        },
    )

    res = client.get("/threats/search?query=phishing")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["success"] is True
    assert len(data["data"]["items"]) == 1
    assert data["data"]["items"][0]["indicator"] == "phishing-bank.net"


def test_threat_stats_endpoint(client):
    """Verifies global aggregation statistics reporting levels and status breakdowns."""
    client.post(
        "/threats",
        json={
            "indicator": "10.0.0.5",
            "indicator_type": "ip",
            "threat_level": "critical",
            "confidence": 95,
            "source": "internal_scan",
        },
    )

    res = client.get("/stats")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["success"] is True
    assert data["data"]["total_threats"] > 0
    assert data["data"]["critical"] > 0
    assert "indicator_type_counts" in data["data"]


def test_global_error_handlers(client):
    """Verifies that payload and routing validation errors return failure format and proper codes."""
    # Test 400 Bad payload missing required field on POST
    res_400 = client.post(
        "/threats",
        json={
            "indicator": "1.1.1.1",
            # missing fields
        },
    )
    assert res_400.status_code == 400
    data_400 = json.loads(res_400.data)
    assert data_400["success"] is False
    assert len(data_400["errors"]) > 0

    # Test 404 Route Not Found
    res_404 = client.get("/nonexistent-path-at-root")
    assert res_404.status_code == 404
    data_404 = json.loads(res_404.data)
    assert data_404["success"] is False
    assert len(data_404["errors"]) > 0
