import requests
import json
import uuid
import psycopg2
import os

BASE_URL = 'http://localhost/api/v1'
EVIDENCE_FILE = 'tests/artifacts/audit_evidence.txt'

def log_evidence(step, data):
    with open(EVIDENCE_FILE, 'a') as f:
        f.write(f"\n{'='*50}\n[STEP] {step}\n{'='*50}\n")
        f.write(f"{data}\n")
    print(f"[STEP] {step}")
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2))

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        print(f"Login failed for {username}: {r.status_code} {r.text}")
        return None
    token = r.json()['data']['access_token']
    return {"Authorization": f"Bearer {token}"}

def verify():
    if os.path.exists(EVIDENCE_FILE):
        os.remove(EVIDENCE_FILE)
    
    admin_headers = login("admin", "secret123")
    if not admin_headers:
        print("Admin login failed")
        return
        
    r = requests.get(f"{BASE_URL}/resources", headers=admin_headers)
    resources = r.json().get('data', [])
    res_id = resources[0]['id'] if resources else None
    
    # 1. Create User via API
    username = f"audit_user_{uuid.uuid4().hex[:6]}"
    user_payload = {
        "employee_id": f"EMP_{uuid.uuid4().hex[:6]}",
        "username": username,
        "email": f"{username}@test.com",
        "full_name": "Audit Test User",
        "password": "Password123!"
    }
    r = requests.post(f"{BASE_URL}/users", headers=admin_headers, json=user_payload)
    if r.status_code != 201:
        print(f"Failed to create user: {r.status_code} {r.text}")
        return
    user_id = r.json()['data']['id']
    
    # 2. Get SOC_ANALYST role and assign to user
    r = requests.get(f"{BASE_URL}/roles", headers=admin_headers)
    roles = r.json()['data']
    soc_role_id = next(role['id'] for role in roles if role['role_code'] == 'SOC_ANALYST')
    
    r = requests.post(f"{BASE_URL}/users/{user_id}/roles", headers=admin_headers, json={"role_id": soc_role_id})
    if r.status_code != 201:
        print(f"Failed to assign role: {r.status_code} {r.text}")
        return
    
    # 3. Setup Policy in DB
    conn = psycopg2.connect("postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db")
    cur = conn.cursor()
    cur.execute(f"INSERT INTO role_permissions (role_id, permission_id) VALUES ('{soc_role_id}', (SELECT id FROM permissions WHERE permission_code = 'PERM_VAULT_READ')) ON CONFLICT DO NOTHING")
    cur.execute(f"DELETE FROM resource_access_policies WHERE resource_id = '{res_id}' AND role_id = '{soc_role_id}'")
    cur.execute(f"INSERT INTO resource_access_policies (id, resource_id, role_id, approval_required, created_at, updated_at) VALUES ('{uuid.uuid4()}', '{res_id}', '{soc_role_id}', true, now(), now())")
    conn.commit()

    # 4. Create Secret
    secret_payload = {"resource_id": res_id, "payload": "audit_secret"}
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json=secret_payload)
    log_evidence("Create Secret API", {"status": r.status_code, "response": r.json()})
    secret_id = r.json()['data']['id']
    
    # 5. User requests access
    user_headers = login(username, "Password123!")
    req_payload = {
        "requested_resource_id": res_id,
        "business_justification": "Need access for testing audit",
        "duration_minutes": 60
    }
    r = requests.post(f"{BASE_URL}/access-requests", headers=user_headers, json=req_payload)
    log_evidence("Request Access API", {"status": r.status_code, "response": r.json()})
    request_id = r.json()['data']['id']
    
    # 6. Admin approves access
    approve_payload = {"justification": "Approved for audit"}
    r = requests.post(f"{BASE_URL}/access-requests/{request_id}/approve", headers=admin_headers, json=approve_payload)
    log_evidence("Approve Access API", {"status": r.status_code, "response": r.json()})
    
    # 7. User retrieves secret
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=user_headers)
    log_evidence("Retrieve Secret API (Valid)", {"status": r.status_code, "response": r.json()})
    
    # 8. Admin rotates secret
    rotate_payload = {"payload": "audit_secret_v2", "resource_id": "26098556-6b60-4f56-a5fe-37855efeedf5"}
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/rotate", headers=admin_headers, json=rotate_payload)
    log_evidence("Rotate Secret API", {"status": r.status_code, "response": r.json()})
    
    # 9. Admin disables secret
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/disable", headers=admin_headers)
    log_evidence("Disable Secret API", {"status": r.status_code, "response": r.json()})

    # 10. Admin deletes secret
    r = requests.delete(f"{BASE_URL}/vault/secrets/{secret_id}", headers=admin_headers)
    log_evidence("Delete Secret API", {"status": r.status_code, "response": r.json()})

    # 11. Unauthorized retrieve (Negative Path)
    # Create another secret first for this test, since the first one is deleted
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json={"resource_id": res_id, "payload": "unauth_secret"})
    unauth_secret_id = r.json()['data']['id']
    
    # Create user with no access request
    unauth_user = f"unauth_{uuid.uuid4().hex[:6]}"
    requests.post(f"{BASE_URL}/users", headers=admin_headers, json={
        "employee_id": f"EMP_{uuid.uuid4().hex[:6]}",
        "username": unauth_user,
        "email": f"{unauth_user}@test.com",
        "full_name": "Unauth Test User",
        "password": "Password123!"
    })
    
    unauth_headers = login(unauth_user, "Password123!")
    r = requests.post(f"{BASE_URL}/vault/secrets/{unauth_secret_id}/retrieve", headers=unauth_headers)
    log_evidence("Retrieve Secret API (Unauthorized)", {"status": r.status_code, "response": r.json()})

    # VERIFY AUDIT LOGS IN DATABASE
    print("\n--- Verifying Audit DB ---")
    
    queries = {
        "SECRET_CREATED": f"SELECT count(*) FROM audit_logs WHERE action = 'SECRET_CREATED' AND resource_id = '{secret_id}'",
        "ACCESS_REQUEST_CREATED": f"SELECT count(*) FROM audit_logs WHERE resource_type = 'access_requests' AND resource_id = '{request_id}' AND action = 'ACCESS_REQUEST_CREATED'",
        "APPROVAL_APPROVED": f"SELECT count(*) FROM audit_logs WHERE action = 'approval.approved' AND resource_type = 'approval_workflows' AND approval_workflow_id IN (SELECT id FROM approval_workflows WHERE access_request_id = '{request_id}')",
        "SECRET_RETRIEVED": f"SELECT count(*) FROM audit_logs WHERE action = 'SECRET_RETRIEVED' AND resource_id = '{secret_id}'",
        "SECRET_ROTATED": f"SELECT count(*) FROM audit_logs WHERE action = 'SECRET_ROTATED' AND resource_id = '{secret_id}'",
        "SECRET_DISABLED": f"SELECT count(*) FROM audit_logs WHERE action = 'SECRET_DISABLED' AND resource_id = '{secret_id}'",
        "SECRET_DELETED": f"SELECT count(*) FROM audit_logs WHERE action = 'SECRET_DELETED' AND resource_id = '{secret_id}'",
        "SECRET_RETRIEVAL_FAILED": f"SELECT count(*) FROM audit_logs WHERE action = 'SECRET_RETRIEVAL_FAILED' AND resource_id = '{unauth_secret_id}'",
    }
    
    results = []
    results.append("| Operation | Expected audit event | Count | Result |")
    results.append("| --- | --- | --- | --- |")
    for op, q in queries.items():
        cur.execute(q)
        count = cur.fetchone()[0]
        status = "PASS" if count >= 1 else "FAIL"
        results.append(f"| {op} | {op} | {count} | {status} |")
        
    log_evidence("Audit DB Verification", "\n".join(results))
    
    # Critical check: DB Vault Secret Tombstone
    cur.execute(f"SELECT status FROM vault_secrets WHERE id = '{secret_id}'")
    db_status = cur.fetchone()[0]
    
    cur.execute(queries['SECRET_DELETED'])
    delete_audit_count = cur.fetchone()[0]
    
    critical_check = f"Secret Status: {db_status}\nAudit Record Count: {delete_audit_count}\n"
    if db_status.upper() == 'TOMBSTONED' and delete_audit_count >= 1:
        critical_check += "CRITICAL CHECK: PASS (Tombstoned record exists and audit remains)"
    else:
        critical_check += "CRITICAL CHECK: FAIL"
        
    log_evidence("Critical Check: Tombstone Persistence", critical_check)

    conn.close()

if __name__ == '__main__':
    verify()
