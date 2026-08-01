def test_auth_missing_token_returns_401(client):
    resp = client.get("/users")
    assert resp.status_code == 401
    assert "Missing or invalid authorization header" in resp.json.get("errors", [])


def test_auth_invalid_token_returns_401(client):
    resp = client.get("/users", headers={"Authorization": "Bearer invalid.token.value"})
    assert resp.status_code == 401
    assert "Invalid token" in resp.json.get("errors", [])


def test_auth_tampered_signature_returns_401(client, normal_token):
    resp = client.get(
        "/users", headers={"Authorization": f"Bearer {normal_token}tampered"}
    )
    assert resp.status_code == 401
    assert "Invalid token" in resp.json.get("errors", [])
