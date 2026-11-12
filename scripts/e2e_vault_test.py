import json
import subprocess

import requests

BASE_URL = "http://localhost:8080/api/v1"

def run_test():
    print("--- Test 1: Login ---")
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "secret123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["data"]["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    print("Admin logged in successfully.")

    # Get admin role ID exactly
    resp = session.get(f"{BASE_URL}/roles")
    roles = resp.json()["data"]
    admin_role_id = next(r["id"] for r in roles if r["role_code"] == "ADMIN")

    print("\n--- Setup: Grant Vault Permissions to Admin ---")
    vault_perms = [
        {"permission_code": "PERM_VAULT_CREATE", "permission_name": "Vault Create", "action": "create"},
        {"permission_code": "PERM_VAULT_READ", "permission_name": "Vault Read", "action": "read"},
        {"permission_code": "PERM_VAULT_UPDATE", "permission_name": "Vault Update", "action": "update"},
        {"permission_code": "PERM_VAULT_DELETE", "permission_name": "Vault Delete", "action": "delete"}
    ]
    for p in vault_perms:
        p_resp = session.post(f"{BASE_URL}/permissions", json=p)
        if p_resp.status_code == 201:
            pid = p_resp.json()["data"]["id"]
            assign_resp = session.post(f"{BASE_URL}/roles/{admin_role_id}/permissions", json={"permission_id": pid})
            print(f"Created and assigned {p['permission_code']}: {assign_resp.status_code}")
        else:
            existing_resp = session.get(f"{BASE_URL}/permissions?search={p['permission_code']}")
            existing = existing_resp.json().get("data", [])
            if existing:
                pid = existing[0]["id"]
                assign_resp = session.post(f"{BASE_URL}/roles/{admin_role_id}/permissions", json={"permission_id": pid})
                print(f"Assigned existing {p['permission_code']}: {assign_resp.status_code}")
            else:
                print(f"Failed to create {p['permission_code']}: {p_resp.text}")
                raise Exception(f"Could not create permission {p['permission_code']}")

    # Re-login admin to refresh token with new permissions
    resp = session.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "secret123"})
    token = resp.json()["data"]["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})

    print("\n--- Test 2: Create Resource ---")
    resource_payload = {
        "resource_name": "Production Database",
        "resource_code": "PROD-DB-01",
        "resource_type": "database",
        "status": "active"
    }
    resp = session.post(f"{BASE_URL}/resources", json=resource_payload)
    if resp.status_code == 201:
        resource_id = resp.json()["data"]["id"]
        print(f"Resource created: {resource_id}")
    elif resp.status_code == 200:
        resource_id = resp.json()["data"]["id"]
        print(f"Resource updated: {resource_id}")
    else:
        resp = session.get(f"{BASE_URL}/resources?search=PROD-DB-01")
        resources = resp.json().get("data", [])
        if not resources:
            print(f"Failed to create or find resource: {resp.text}")
            return
        resource_id = resources[0]["id"]
        print(f"Resource found: {resource_id}")

    print("\n--- Test 3: Create Vault Secret ---")
    secret_payload = json.dumps({"username": "root", "password": "Test@123"})
    resp = session.post(f"{BASE_URL}/vault/secrets", json={
        "resource_id": resource_id,
        "payload": secret_payload
    })
    assert resp.status_code == 201, f"Secret creation failed: {resp.text}"
    secret_id = resp.json()["id"]
    print(f"Secret created: {secret_id}")

    print("\n--- Test 4: Database Verification ---")
    result = subprocess.run([
        "docker", "exec", "opsforge-postgres", "psql", "-U", "opsforge", "-d", "opsforge_db", "-c", "SELECT encrypted_payload FROM vault_secret_versions;"
    ], capture_output=True, text=True)
    output = result.stdout
    print("DB Output:")
    print(output)
    if "root" in output or "Test@123" in output:
        print("FAIL: Plaintext found in DB!")
    else:
        print("PASS: No plaintext found in DB.")

    print("\n--- Test 5: Reveal Secret ---")
    resp = session.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve")
    assert resp.status_code == 200, f"Reveal failed: {resp.text}"
    payload_retrieved = resp.json()["payload"]
    assert "Test@123" in payload_retrieved, f"Expected password not found in payload: {payload_retrieved}"
    print(f"Secret revealed successfully: {payload_retrieved}")

    print("\n--- Test 6: Unauthorized User ---")
    import uuid
    rand_id = str(uuid.uuid4())[:8]
    user_payload = {
        "username": f"testuser_{rand_id}",
        "email": f"testuser_{rand_id}@example.com",
        "full_name": "Test User",
        "employee_id": f"EMP{rand_id}",
        "password": "user1234"
    }
    resp = session.post(f"{BASE_URL}/users", json=user_payload)
    assert resp.status_code == 201, f"User creation failed: {resp.text}"

    user_session = requests.Session()
    resp = user_session.post(f"{BASE_URL}/auth/login", json={"username": f"testuser_{rand_id}", "password": "user1234"})
    assert resp.status_code == 200, f"User login failed: {resp.text}"
    u_token = resp.json()["data"]["access_token"]
    user_session.headers.update({"Authorization": f"Bearer {u_token}"})

    resp = user_session.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve")
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    print(f"Unauthorized user blocked correctly. Response: {resp.text}")

    print("\n--- All Tests Passed ---")

if __name__ == "__main__":
    run_test()
