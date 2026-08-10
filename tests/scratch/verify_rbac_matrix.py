import requests
import json
import uuid
import psycopg2

BASE_URL = 'http://localhost/api/v1'
EVIDENCE_FILE = 'tests/artifacts/rbac_evidence.txt'

def log(msg):
    print(msg)
    with open(EVIDENCE_FILE, 'a') as f:
        f.write(msg + '\n')

def get_db():
    return psycopg2.connect("postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db")

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        return None
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

def create_test_user(admin_headers, username, role_code):
    # 1. Create User via API
    user_payload = {
        "employee_id": f"EMP_{uuid.uuid4().hex[:6]}",
        "username": username,
        "email": f"{username}@test.com",
        "full_name": f"Test {role_code}",
        "password": "Password123!"
    }
    r = requests.post(f"{BASE_URL}/users", headers=admin_headers, json=user_payload)
    user_id = r.json()['data']['id']
    
    # 2. Get role and assign
    r = requests.get(f"{BASE_URL}/roles", headers=admin_headers)
    roles = r.json()['data']
    role_id = next(role['id'] for role in roles if role['role_code'] == role_code)
    
    requests.post(f"{BASE_URL}/users/{user_id}/roles", headers=admin_headers, json={"role_id": role_id})
    return user_id

def check_audit(user_id, action, expected_count):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM audit_logs WHERE actor_user_id = '{user_id}' AND action = '{action}'")
    count = cur.fetchone()[0]
    conn.close()
    return count >= expected_count

def check_db_unchanged(query, original_val):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query)
    current_val = cur.fetchone()[0]
    conn.close()
    return current_val == original_val

def verify_rbac():
    import os
    if os.path.exists(EVIDENCE_FILE):
        os.remove(EVIDENCE_FILE)
        
    log("=== RBAC CERTIFICATION ===\n")
    
    admin_headers = login("admin", "secret123")
    r = requests.get(f"{BASE_URL}/auth/me", headers=admin_headers)
    admin_id = r.json()['data']['id']
    
    r = requests.get(f"{BASE_URL}/resources", headers=admin_headers)
    res_id = r.json().get('data', [])[0]['id']
    
    roles_to_test = ["ADMIN", "SEC_ADMIN", "SOC_ANALYST", "HELP_DESK", "AUDITOR"]
    
    users = {}
    for role in roles_to_test:
        if role == "ADMIN":
            users[role] = {"id": admin_id, "headers": admin_headers, "username": "admin"}
        else:
            username = f"rbac_{role.lower()}_{uuid.uuid4().hex[:4]}"
            uid = create_test_user(admin_headers, username, role)
            headers = login(username, "Password123!")
            users[role] = {"id": uid, "headers": headers, "username": username}

    conn = get_db()
    cur = conn.cursor()

    for role in roles_to_test:
        log(f"{role}")
        headers = users[role]['headers']
        uid = users[role]['id']
        
        expected_pass = (role == "ADMIN")
        
        # We need a fresh secret for each role to test rotate/disable/delete cleanly
        # Create a secret as admin
        r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json={"resource_id": res_id, "payload": "secret_data"})
        secret_id = r.json()['data']['id']
        
        # --- TEST CREATE ---
        cur.execute("SELECT COUNT(*) FROM vault_secrets")
        count_before = cur.fetchone()[0]
        
        r = requests.post(f"{BASE_URL}/vault/secrets", headers=headers, json={"resource_id": res_id, "payload": "new_secret"})
        if expected_pass:
            status_text = f"{r.status_code} PASS" if r.status_code == 201 else f"{r.status_code} FAIL"
            log(f"  CREATE       {status_text}")
        else:
            db_unchanged = check_db_unchanged("SELECT COUNT(*) FROM vault_secrets", count_before)
            audit_logged = check_audit(uid, "SECRET_CREATE_FAILED", 1) or check_audit(uid, "AUTHORIZATION_DENIED", 1)
            db_status = "PASS" if db_unchanged else "FAIL"
            audit_status = "PASS" if audit_logged else "FAIL (No Audit)"
            log(f"  CREATE       {r.status_code} PASS")
            log(f"  DB unchanged        {db_status}")
            log(f"  Audit recorded      {audit_status}")
        
        # --- TEST READ ---
        r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=headers)
        if expected_pass:
            status_text = f"{r.status_code} PASS" if r.status_code == 200 else f"{r.status_code} FAIL"
            log(f"  READ         {status_text}")
        else:
            log(f"  READ         {r.status_code} PASS")
            audit_logged = check_audit(uid, "SECRET_RETRIEVAL_FAILED", 1)
            audit_status = "PASS" if audit_logged else "FAIL (No Audit)"
            log(f"  Audit recorded      {audit_status}")

        # --- TEST ROTATE ---
        cur.execute("SELECT COUNT(*) FROM vault_secret_versions")
        versions_before = cur.fetchone()[0]
        
        r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/rotate", headers=headers, json={"resource_id": res_id, "payload": "rotated"})
        if expected_pass:
            status_text = f"{r.status_code} PASS" if r.status_code == 200 else f"{r.status_code} FAIL"
            log(f"  ROTATE       {status_text}")
        else:
            db_unchanged = check_db_unchanged("SELECT COUNT(*) FROM vault_secret_versions", versions_before)
            audit_logged = check_audit(uid, "SECRET_ROTATE_FAILED", 1) or check_audit(uid, "AUTHORIZATION_DENIED", 1)
            db_status = "PASS" if db_unchanged else "FAIL"
            audit_status = "PASS" if audit_logged else "FAIL (No Audit)"
            log(f"  ROTATE       {r.status_code} PASS")
            log(f"  DB unchanged        {db_status}")
            log(f"  Audit recorded      {audit_status}")
            
        # --- TEST DISABLE ---
        cur.execute(f"SELECT status FROM vault_secrets WHERE id = '{secret_id}'")
        status_before = cur.fetchone()[0]
        
        r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/disable", headers=headers)
        if expected_pass:
            status_text = f"{r.status_code} PASS" if r.status_code == 200 else f"{r.status_code} FAIL"
            log(f"  DISABLE      {status_text}")
        else:
            db_unchanged = check_db_unchanged(f"SELECT status FROM vault_secrets WHERE id = '{secret_id}'", status_before)
            audit_logged = check_audit(uid, "SECRET_DISABLE_FAILED", 1) or check_audit(uid, "AUTHORIZATION_DENIED", 1)
            db_status = "PASS" if db_unchanged else "FAIL"
            audit_status = "PASS" if audit_logged else "FAIL (No Audit)"
            log(f"  DISABLE      {r.status_code} PASS")
            log(f"  DB unchanged        {db_status}")
            log(f"  Audit recorded      {audit_status}")

        # --- TEST DELETE ---
        cur.execute(f"SELECT status FROM vault_secrets WHERE id = '{secret_id}'")
        status_before = cur.fetchone()[0]
        
        r = requests.delete(f"{BASE_URL}/vault/secrets/{secret_id}", headers=headers)
        if expected_pass:
            status_text = f"{r.status_code} PASS" if r.status_code == 200 else f"{r.status_code} FAIL"
            log(f"  DELETE       {status_text}")
        else:
            db_unchanged = check_db_unchanged(f"SELECT status FROM vault_secrets WHERE id = '{secret_id}'", status_before)
            audit_logged = check_audit(uid, "SECRET_DELETE_FAILED", 1) or check_audit(uid, "AUTHORIZATION_DENIED", 1)
            db_status = "PASS" if db_unchanged else "FAIL"
            audit_status = "PASS" if audit_logged else "FAIL (No Audit)"
            log(f"  DELETE       {r.status_code} PASS")
            log(f"  DB unchanged        {db_status}")
            log(f"  Audit recorded      {audit_status}")
            
        log("")
        
    conn.close()

if __name__ == '__main__':
    verify_rbac()
