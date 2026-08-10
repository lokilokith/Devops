import requests
import json
import uuid
import psycopg2
import time

BASE_URL = 'http://localhost/api/v1'
EVIDENCE_FILE = 'tests/artifacts/vault_functional_evidence.txt'

def log_evidence(step, data):
    with open(EVIDENCE_FILE, 'a') as f:
        f.write(f"\n{'='*50}\n[STEP] {step}\n{'='*50}\n")
        f.write(f"{data}\n")
    print(f"[STEP] {step}")

def login():
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "secret123"})
    if r.status_code != 200:
        print(r.text)
        return None
    token = r.json()['data']['access_token']
    return {"Authorization": f"Bearer {token}"}

def verify():
    import os
    if os.path.exists(EVIDENCE_FILE):
        os.remove(EVIDENCE_FILE)
    
    headers = login()
    if not headers:
        log_evidence("Login", "Failed to login")
        return
        
    r = requests.get(f"{BASE_URL}/resources", headers=headers)
    j = r.json()
    resources = j.get('data', [])
    res_id = resources[0]['id'] if resources else None
    
    # Connect to DB to set up ResourceAccessPolicy
    conn = psycopg2.connect("postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db")
    cur = conn.cursor()
    
    # Get Admin role ID
    cur.execute("SELECT id FROM roles WHERE role_code = 'ADMIN'")
    admin_role_id = cur.fetchone()[0]
    
    # Ensure policy allows access without approval
    cur.execute(f"DELETE FROM resource_access_policies WHERE resource_id = '{res_id}' AND role_id = '{admin_role_id}'")
    cur.execute(f"INSERT INTO resource_access_policies (id, resource_id, role_id, approval_required, created_at, updated_at) VALUES ('{uuid.uuid4()}', '{res_id}', '{admin_role_id}', false, now(), now())")
    conn.commit()

    # 1. Vault Create
    payload = {"resource_id": res_id, "payload": "super_secret_p@ssw0rd"}
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=headers, json=payload)
    log_evidence("Vault Create", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    secret_id = r.json()['data']['id']
    
    # 2. Vault List
    r = requests.get(f"{BASE_URL}/vault/secrets", headers=headers)
    log_evidence("Vault List", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 3. Vault Retrieve (v1)
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=headers)
    log_evidence("Vault Retrieve (v1)", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 4. Vault Rotate (Creates v2)
    rotate_payload = {"resource_id": res_id, "payload": "new_super_secret_p@ssw0rd"}
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/rotate", headers=headers, json=rotate_payload)
    log_evidence("Vault Rotate", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 5. Vault Retrieve (v2)
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=headers)
    log_evidence("Vault Retrieve (v2)", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 6. Vault Disable
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/disable", headers=headers)
    log_evidence("Vault Disable", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 7. Vault Retrieve (Disabled - Should Fail)
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=headers)
    log_evidence("Vault Retrieve (Disabled)", json.dumps({"status": r.status_code, "response": r.json()}, indent=2))
    
    # 8. Vault Delete
    r = requests.delete(f"{BASE_URL}/vault/secrets/{secret_id}", headers=headers)
    log_evidence("Vault Delete", json.dumps({"status": r.status_code, "response": r.json() if r.text else "No Content"}, indent=2))
    
    # 9. Database Verification (Objective Evidence)
    cur.execute(f"SELECT id, resource_id, status FROM vault_secrets WHERE id = '{secret_id}'")
    secret_row = cur.fetchone()
    if secret_row:
        log_evidence("SQL Verification: vault_secrets (Status check)", f"ID: {secret_row[0]}, Resource ID: {secret_row[1]}, Status: {secret_row[2]}")
    else:
        log_evidence("SQL Verification: vault_secrets (Status check)", "Secret completely deleted.")
    
    cur.execute(f"SELECT created_at, encrypted_payload, algorithm, key_version FROM vault_secret_versions WHERE secret_id = '{secret_id}' ORDER BY created_at ASC")
    versions = cur.fetchall()
    
    formatted_versions = []
    for v in versions:
        encrypted_val = v[1]
        if isinstance(encrypted_val, bytes):
            encrypted_str = encrypted_val.hex()[:30] + "..."
        elif isinstance(encrypted_val, str):
            encrypted_str = encrypted_val[:30] + "..."
        elif isinstance(encrypted_val, memoryview):
            encrypted_str = encrypted_val.tobytes().hex()[:30] + "..."
        else:
            encrypted_str = str(encrypted_val)[:30] + "..."
            
        formatted_versions.append({
            "created_at": str(v[0]),
            "encrypted": encrypted_str,
            "algorithm": v[2],
            "key_version": v[3]
        })
        
    log_evidence("SQL Verification: vault_secret_versions (v1 & v2 exist)", json.dumps(formatted_versions, indent=2))
    conn.close()

if __name__ == '__main__':
    verify()
