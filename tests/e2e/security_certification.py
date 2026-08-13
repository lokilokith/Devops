import requests
import uuid
import sys
import psycopg2

BASE_URL = "http://localhost/api/v1"
ADMIN_CREDS = {"username": "admin", "password": "secret123"}
evidence_lines = []
DB_URL = "postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db"

def report(test_cat, scenario, expected, actual, passed):
    result = "PASS" if passed else "FAIL"
    evidence_lines.append(f"| {test_cat} | {scenario} | {expected} | {actual} | **{result}** |")
    if not passed:
        print(f"FAIL: {test_cat} - {scenario}. Expected: {expected}, Actual: {actual}")

def run_checks():
    evidence_lines.append("# Security Negative Certification Evidence\n")
    evidence_lines.append("| Test Category | Attack/Scenario | Expected | Actual | Result |")
    evidence_lines.append("|---|---|---|---|---|")

    # 1. JWT Tests
    # Missing token
    r = requests.get(f"{BASE_URL}/vault/secrets")
    report("JWT", "Missing token", "Status 401", f"Status {r.status_code}", r.status_code == 401)
    
    # Malformed token
    r = requests.get(f"{BASE_URL}/vault/secrets", headers={"Authorization": "Bearer malformed"})
    report("JWT", "Malformed token", "Status 401/422", f"Status {r.status_code}", r.status_code in [401, 422])
    
    # Invalid signature
    invalid_sig = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.invalid"
    r = requests.get(f"{BASE_URL}/vault/secrets", headers={"Authorization": f"Bearer {invalid_sig}"})
    report("JWT", "Invalid signature", "Status 401/422", f"Status {r.status_code}", r.status_code in [401, 422])

    # Login as admin for further tests
    r = requests.post(f"{BASE_URL}/auth/login", json=ADMIN_CREDS)
    if r.status_code != 200:
        print("FAIL: Could not login admin.")
        sys.exit(1)
    admin_token = r.json()["data"]["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Input Validation
    # Invalid UUID
    r = requests.get(f"{BASE_URL}/users/not-a-uuid", headers=admin_headers)
    report("Input Validation", "Invalid UUID format in URL", "Status 404/400/405/422", f"Status {r.status_code}", r.status_code in [404, 400, 405, 422])
    
    # Missing fields
    r = requests.post(f"{BASE_URL}/users", headers=admin_headers, json={"username": "test"})
    report("Input Validation", "Missing required fields (POST /users)", "Status 400/422", f"Status {r.status_code}", r.status_code in [400, 422])
    
    # Malformed JSON
    headers_json = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    r = requests.post(f"{BASE_URL}/users", headers=headers_json, data="{'bad': 'json'")
    report("Input Validation", "Malformed JSON payload", "Status 400", f"Status {r.status_code}", r.status_code == 400)
    
    # Invalid Enum (assuming roles requires status string)
    r = requests.post(f"{BASE_URL}/roles", headers=admin_headers, json={"role_name": "BAD_ROLE", "status": "INVALID_ENUM", "description": "foo"})
    report("Input Validation", "Invalid Enum value (RoleStatus)", "Status 400/422", f"Status {r.status_code}", r.status_code in [400, 422])
    
    # 3. Injection
    # SQL Injection-style input
    r = requests.get(f"{BASE_URL}/users?search=admin' OR '1'='1", headers=admin_headers)
    report("Injection", "SQL injection string in search query", "Status 200 (Safe)", f"Status {r.status_code}", r.status_code == 200)

    # XSS-style input
    xss_payload = "<script>alert(1)</script>"
    # Try to create a resource with XSS in name
    r = requests.post(f"{BASE_URL}/resources", headers=admin_headers, json={"name": xss_payload, "resource_type": "Server"})
    # It might be allowed and stored safely or blocked by validation. We just care it doesn't crash (500)
    report("Injection", "XSS string in resource name", "Status != 500", f"Status {r.status_code}", r.status_code != 500)

    # 4. Authorization & Resource-state attacks
    # Setup test resource and secret
    res_name = f"TestRes-{uuid.uuid4().hex[:6]}"
    res_code = f"TEST_RES_{uuid.uuid4().hex[:6].upper()}"
    r = requests.post(f"{BASE_URL}/resources", headers=admin_headers, json={"resource_code": res_code, "resource_name": res_name, "resource_type": "server", "description": "foo", "status": "active", "environment": "prod", "criticality": "low"})
    if r.status_code != 201:
        print(f"FAIL: Could not create resource. Status: {r.status_code}, {r.text}")
        sys.exit(1)
    res_id = r.json()["data"]["id"]

    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json={"resource_id": res_id, "payload": "sensitive-data"})
    if r.status_code != 201:
        print("FAIL: Could not create secret.")
        sys.exit(1)
    secret_id = r.json()["data"]["id"]

    # Retrieve active secret (without access request)
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=admin_headers, json={"justification": "test"})
    report("Resource State", "Retrieve active secret without access request", "Status 403", f"Status {r.status_code}", r.status_code == 403)

    # Disable secret
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/disable", headers=admin_headers)
    report("Resource State", "Disable secret", "Status 200", f"Status {r.status_code}", r.status_code == 200)

    # Retrieve disabled secret
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=admin_headers, json={"justification": "test"})
    report("Resource State", "Retrieve disabled secret", "Status 400/403/409", f"Status {r.status_code}", r.status_code in [400, 403, 409])

    # Rotate disabled secret
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/rotate", headers=admin_headers, json={"resource_id": res_id, "payload": "new-data"})
    report("Resource State", "Rotate disabled secret", "Status 400/409", f"Status {r.status_code}", r.status_code in [400, 409])

    # 5. Sensitive-data checks
    # DB plain text check
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT encrypted_payload FROM vault_secret_versions WHERE secret_id = %s", (secret_id,))
    out = cur.fetchone()[0]
    is_encrypted = "sensitive-data" not in str(out) and len(str(out)) > 20
    report("Sensitive Data", "Plaintext not in DB", "Encrypted payload", "Encrypted" if is_encrypted else "Plaintext leaked", is_encrypted)
    
    # Audit log check (no plaintext in audit logs)
    cur.execute("SELECT details FROM audit_logs ORDER BY created_at DESC LIMIT 10")
    audit_rows = cur.fetchall()
    audit_clean = True
    for row in audit_rows:
        if row[0] and "sensitive-data" in str(row[0]):
            audit_clean = False
    report("Sensitive Data", "Plaintext not in Audit logs", "Clean audit logs", "Clean" if audit_clean else "Plaintext leaked", audit_clean)
    conn.close()

    # Write evidence
    with open("docs/evidence/security_evidence.md", "w") as f:
        f.write("\n".join(evidence_lines) + "\n")

    failures = sum(1 for line in evidence_lines if "**FAIL**" in line)
    if failures > 0:
        print(f"Security Certification Failed with {failures} violations.")
        sys.exit(1)
    else:
        print("Security Certification Passed: 0 violations.")
        sys.exit(0)

if __name__ == "__main__":
    run_checks()
