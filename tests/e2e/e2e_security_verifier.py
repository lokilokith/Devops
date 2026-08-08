import requests
import uuid
import sys
import os

BASE_URL = 'http://localhost:5000'

def print_step(msg):
    print(f"\n{'='*50}\n[STEP] {msg}\n{'='*50}")

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        return None
    token = r.json()['data']['access_token']
    return {"Authorization": f"Bearer {token}"}

def main():
    admin_headers = login("admin", "secret123")
    if not admin_headers:
        print("FAIL: Could not login as admin.")
        sys.exit(1)

    print_step("Phase B: Authentication & Payload Security")
    
    # Missing JWT
    r = requests.get(f"{BASE_URL}/vault/secrets")
    assert r.status_code == 401, f"Missing JWT returned {r.status_code}"

    # Invalid JWT
    r = requests.get(f"{BASE_URL}/vault/secrets", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert r.status_code == 401, f"Invalid JWT returned {r.status_code}"

    # Invalid UUID in path
    r = requests.get(f"{BASE_URL}/vault/secrets/not-a-uuid", headers=admin_headers)
    assert r.status_code in [400, 404, 422, 500], f"Invalid UUID returned {r.status_code}"

    # Missing payload fields
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json={"resource_id": str(uuid.uuid4())})
    assert r.status_code in [400, 422], f"Missing payload returned {r.status_code}"

    print_step("Phase B.1: Vault Security Validation (Plain-text & Versioning)")

    # Create a resource
    res_id = requests.post(f"{BASE_URL}/resources", headers=admin_headers, json={
        "resource_code": f"SEC_TEST_{uuid.uuid4().hex[:4].upper()}",
        "resource_name": f"Sec Test {uuid.uuid4().hex[:4]}",
        "description": "Test"
    }).json()['data']['id']
    
    # Create a secret
    payload_plaintext = "plaintext_secret_value"
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json={"resource_id": res_id, "payload": payload_plaintext})
    secret_id = r.json()['data']['id']

    import psycopg2
    conn = psycopg2.connect("postgresql://opsforge:opsforge_pass@opsforge-postgres/opsforge_db")
    cur = conn.cursor()
    cur.execute(f"SELECT encrypted_payload::text FROM vault_secret_versions WHERE secret_id = '{secret_id}'")
    out = cur.fetchone()[0]
    
    assert payload_plaintext not in out, "PLAINTEXT SECRET FOUND IN DATABASE!"
    assert len(out) > 30, f"Payload does not look encrypted: {out}"

    # Verify version increment
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/rotate", headers=admin_headers, json={"payload": "new_rotated_value", "resource_id": res_id})
    assert r.status_code == 200, "Failed to rotate"
    
    # Retrieve should now return the rotated value (implicit version increment)
    cur.execute(f"SELECT row_version FROM vault_secrets WHERE id = '{secret_id}'")
    out_version = str(cur.fetchone()[0])
    assert int(out_version) > 1, f"Version did not increment: {out_version}"

    print("ALL SECURITY TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    main()
