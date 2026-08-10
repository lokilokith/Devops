import requests
import json
import uuid
import psycopg2

BASE_URL = 'http://localhost/api/v1'
EVIDENCE_FILE = 'tests/artifacts/approval_workflow_evidence.txt'

def log_evidence(step, data):
    with open(EVIDENCE_FILE, 'a') as f:
        f.write(f"\n{'='*50}\n[STEP] {step}\n{'='*50}\n")
        f.write(f"{data}\n")
    print(f"[STEP] {step}")

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        print(f"Login failed for {username}: {r.status_code} {r.text}")
        return None
    token = r.json()['data']['access_token']
    return {"Authorization": f"Bearer {token}"}

def verify():
    import os
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
    username = f"workflow_{uuid.uuid4().hex[:6]}"
    user_payload = {
        "employee_id": f"EMP_{uuid.uuid4().hex[:6]}",
        "username": username,
        "email": f"{username}@test.com",
        "full_name": "Workflow User",
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

    # 4. Make sure a secret exists
    secret_payload = {"resource_id": res_id, "payload": "workflow_secret"}
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json=secret_payload)
    secret_id = r.json()['data']['id']
    
    # 5. User requests access
    user_headers = login(username, "Password123!")
    req_payload = {
        "requested_resource_id": res_id,
        "business_justification": "Need access for testing",
        "duration_minutes": 60
    }
    r = requests.post(f"{BASE_URL}/access-requests", headers=user_headers, json=req_payload)
    log_evidence("Request Access", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    request_id = r.json()['data']['id']
    
    # 6. Admin approves access
    approve_payload = {"justification": "Approved for testing"}
    r = requests.post(f"{BASE_URL}/access-requests/{request_id}/approve", headers=admin_headers, json=approve_payload)
    log_evidence("Approve Access", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 7. User retrieves secret (Must work)
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=user_headers)
    log_evidence("Retrieve (Valid Workflow)", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 8. Expire the workflow via DB
    cur.execute(f"UPDATE access_requests SET requested_end = now() - interval '1 hour' WHERE id = '{request_id}'")
    conn.commit()
    
    # 9. User retrieves secret (Must fail)
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=user_headers)
    log_evidence("Retrieve (Expired Workflow)", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 10. Database Verification
    cur.execute(f"SELECT id, status, requester_id, requested_resource_id, approved_by FROM access_requests WHERE id = '{request_id}'")
    row = cur.fetchone()
    if row:
        log_evidence("SQL Verification: access_requests", f"ID: {row[0]}, Status: {row[1]}, Requester: {row[2]}, Resource: {row[3]}, Approver: {row[4]}")
        
    conn.close()

if __name__ == '__main__':
    verify()
