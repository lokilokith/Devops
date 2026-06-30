"""OpsForge End-to-End Threat Lifecycle Integration Tests.

Validates complete workflow pipelines, statistics updates, and state transitions.
"""

import json


def test_threat_lifecycle_integration_workflow(client):
    """Executes a full end-to-end integration workflow for Threat Intel records."""
    # 1. System Vitality Check
    health_res = client.get("/health")
    assert health_res.status_code == 200

    # 2. Seed a critical threat
    threat_1_payload = {
        "indicator": "198.51.100.25",
        "indicator_type": "ip",
        "threat_level": "critical",
        "confidence": 98,
        "mitre_attack": "T1078",
        "source": "SOC Incident Response",
        "analyst_notes": "Active credential dumping detected from this internal-facing IP",
        "assigned_analyst": "analyst_clara",
        "status": "Open",
        "tags": ["apt", "credential-dumping"],
    }
    create_res = client.post("/threats", json=threat_1_payload)
    assert create_res.status_code == 201
    threat_1 = json.loads(create_res.data)["data"]
    threat_1_id = threat_1["id"]

    # 3. Seed another minor threat
    threat_2_payload = {
        "indicator": "phishing-link-active.ru",
        "indicator_type": "domain",
        "threat_level": "low",
        "confidence": 35,
        "source": "User Submission",
        "status": "Open",
        "tags": ["phishing"],
    }
    create_res2 = client.post("/threats", json=threat_2_payload)
    assert create_res2.status_code == 201

    # 4. Check stats updates
    stats_res = client.get("/threats/stats")
    assert stats_res.status_code == 200
    stats_data = json.loads(stats_res.data)["data"]
    assert stats_data["total"] == 2
    assert stats_data["critical"] == 1
    assert stats_data["indicator_types"]["ip"] == 1
    assert stats_data["indicator_types"]["domain"] == 1

    # 5. Transition threat 1 through its allowed status pipeline
    # Open -> Investigating
    patch_res = client.patch(
        f"/threats/{threat_1_id}/status",
        json={"status": "Investigating", "last_updated_by": "analyst_clara"},
    )
    assert patch_res.status_code == 200

    # Investigating -> Contained
    patch_res = client.patch(
        f"/threats/{threat_1_id}/status",
        json={"status": "Contained", "last_updated_by": "analyst_clara"},
    )
    assert patch_res.status_code == 200

    # Contained -> Closed
    patch_res = client.patch(
        f"/threats/{threat_1_id}/status",
        json={"status": "Closed", "last_updated_by": "analyst_clara"},
    )
    assert patch_res.status_code == 200

    # 6. Verify stats status count change
    stats_res2 = client.get("/threats/stats")
    stats_data2 = json.loads(stats_res2.data)["data"]
    assert stats_data2["open"] == 1  # threat 2
    assert stats_data2["closed"] == 1  # threat 1

    # 7. Blocked: Re-opening closed threat 1
    bad_patch = client.patch(
        f"/threats/{threat_1_id}/status",
        json={"status": "Open", "last_updated_by": "analyst_clara"},
    )
    assert bad_patch.status_code == 400
    bad_data = json.loads(bad_patch.data)
    assert bad_data["success"] is False
    assert "blocked" in bad_data["message"].lower()

    # 8. Clean up threat 1
    del_res = client.delete(f"/threats/{threat_1_id}")
    assert del_res.status_code == 200

    # 9. Verify deletion and stats recount
    stats_res3 = client.get("/threats/stats")
    stats_data3 = json.loads(stats_res3.data)["data"]
    assert stats_data3["total"] == 1
    assert stats_data3["closed"] == 0
