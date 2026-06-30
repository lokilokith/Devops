"""OpsForge Route Controller Unit Tests.

Validates endpoint routing, HTTP status codes, and JSON response models.
"""

import json


def test_api_health_endpoint(client):
    """Verifies that GET /health yields system status statistics in the API format."""
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data)

    assert data["success"] is True
    assert data["message"] == "System status check executed successfully"
    assert "application" in data["data"]
    assert "database" in data["data"]
    assert data["data"]["database"] == "healthy"
    assert data["data"]["version"] == "0.1.0"
    assert data["data"]["environment"] == "testing"
    assert isinstance(data["data"]["uptime"], float)


def test_threats_crud_api_flow(client):
    """Verifies standard CRUD workflow endpoints for Threat records."""
    # 1. Create (POST /threats)
    payload = {
        "indicator": "malware.exe-hash-value",
        "indicator_type": "hash",
        "threat_level": "critical",
        "confidence": 95,
        "mitre_attack": "T1105",
        "source": "VirusTotal Egress",
        "analyst_notes": "Identified download payload",
        "assigned_analyst": "analyst_bob",
        "status": "Open",
        "tags": ["malware", "executable"],
    }
    response = client.post("/threats", json=payload)
    assert response.status_code == 201
    res_data = json.loads(response.data)
    assert res_data["success"] is True
    assert res_data["data"]["indicator"] == "malware.exe-hash-value"
    threat_id = res_data["data"]["id"]

    # 2. List (GET /threats)
    list_response = client.get("/threats")
    assert list_response.status_code == 200
    list_data = json.loads(list_response.data)
    assert list_data["success"] is True
    assert list_data["data"]["total"] == 1
    assert list_data["data"]["items"][0]["id"] == threat_id

    # 3. Read (GET /threats/<id>)
    read_response = client.get(f"/threats/{threat_id}")
    assert read_response.status_code == 200
    read_data = json.loads(read_response.data)
    assert read_data["success"] is True
    assert read_data["data"]["indicator"] == "malware.exe-hash-value"

    # 4. Update (PUT /threats/<id>)
    payload["confidence"] = 80
    payload["analyst_notes"] = "Downgraded severity"
    update_response = client.put(f"/threats/{threat_id}", json=payload)
    assert update_response.status_code == 200
    update_data = json.loads(update_response.data)
    assert update_data["data"]["confidence"] == 80
    assert update_data["data"]["analyst_notes"] == "Downgraded severity"

    # 5. Patch Status (PATCH /threats/<id>/status)
    status_payload = {"status": "Investigating", "last_updated_by": "analyst_alice"}
    patch_response = client.patch(f"/threats/{threat_id}/status", json=status_payload)
    assert patch_response.status_code == 200
    patch_data = json.loads(patch_response.data)
    assert patch_data["data"]["status"] == "Investigating"
    assert patch_data["data"]["last_updated_by"] == "analyst_alice"

    # 6. Delete (DELETE /threats/<id>)
    delete_response = client.delete(f"/threats/{threat_id}")
    assert delete_response.status_code == 200
    delete_data = json.loads(delete_response.data)
    assert delete_data["success"] is True

    # 7. Confirm deletion (GET /threats/<id> -> 404)
    get_deleted = client.get(f"/threats/{threat_id}")
    assert get_deleted.status_code == 404


def test_threat_list_pagination_and_filtering(client):
    """Verifies API filtering, sorting, and pagination logic via query parameters."""
    # Seed threats
    client.post(
        "/threats",
        json={
            "indicator": "1.1.1.1",
            "indicator_type": "ip",
            "threat_level": "low",
            "confidence": 10,
            "source": "feed",
        },
    )
    client.post(
        "/threats",
        json={
            "indicator": "bad.com",
            "indicator_type": "domain",
            "threat_level": "high",
            "confidence": 85,
            "source": "feed",
        },
    )
    client.post(
        "/threats",
        json={
            "indicator": "2.2.2.2",
            "indicator_type": "ip",
            "threat_level": "medium",
            "confidence": 50,
            "source": "feed",
        },
    )

    # Check filtering by indicator type
    response = client.get("/threats?indicator_type=ip")
    data = json.loads(response.data)
    assert len(data["data"]["items"]) == 2

    # Check sorting and pagination limit
    response = client.get("/threats?sort=confidence&order=desc&limit=2")
    data = json.loads(response.data)
    assert len(data["data"]["items"]) == 2
    assert data["data"]["items"][0]["indicator"] == "bad.com"  # 85 confidence
    assert data["data"]["items"][1]["indicator"] == "2.2.2.2"  # 50 confidence


def test_threat_stats_endpoint(client):
    """Verifies that GET /threats/stats yields correct telemetry JSON."""
    client.post(
        "/threats",
        json={
            "indicator": "10.0.0.5",
            "indicator_type": "ip",
            "threat_level": "critical",
            "confidence": 99,
            "source": "feed",
        },
    )

    response = client.get("/threats/stats")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["success"] is True
    assert data["data"]["total"] == 1
    assert data["data"]["critical"] == 1
    assert data["data"]["indicator_types"]["ip"] == 1


def test_global_error_handlers(client):
    """Verifies custom error handlers format 404, 400, and 405 failure payloads uniformly."""
    # Test 404
    res_404 = client.get("/threats/9999")
    assert res_404.status_code == 404
    data_404 = json.loads(res_404.data)
    assert data_404["success"] is False
    assert "not found" in data_404["message"].lower()
    assert isinstance(data_404["errors"], list)

    # Test 400 (Bad payload missing confidence)
    res_400 = client.post(
        "/threats",
        json={
            "indicator": "1.1.1.1",
            "indicator_type": "ip",
            "threat_level": "low",
            "source": "feed",
        },
    )
    assert res_400.status_code == 400
    data_400 = json.loads(res_400.data)
    assert data_400["success"] is False
    assert (
        "confidence" in data_400["message"].lower()
        or "validation" in data_400["message"].lower()
    )

    # Test 405 (Method Not Allowed - POST to stats)
    res_405 = client.post("/threats/stats", json={})
    assert res_405.status_code == 405
    data_405 = json.loads(res_405.data)
    assert data_405["success"] is False
    assert "method" in data_405["message"].lower()
