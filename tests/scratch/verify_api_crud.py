import requests
import uuid
import psycopg2
from pprint import pprint

BASE_URL = 'http://localhost/api/v1'

def log(msg):
    print(msg)

def get_admin_token():
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "secret123"})
    return r.json()["data"]["access_token"]

def main():
    token = get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    log("=== API CRUD VERIFICATION ===")
    
    # 1. Create Permission
    perm_payload = {
        "permission_code": "CERT_TEST_API_PERM",
        "permission_name": "Cert Test API Permission",
        "description": "Used for certification testing",
        "action": "execute"
    }
    log("CREATE: POST /permissions")
    r = requests.post(f"{BASE_URL}/permissions", headers=headers, json=perm_payload)
    if r.status_code != 201:
        log(f"FAIL: {r.status_code} {r.text}")
        return
    perm_id = r.json()["data"]["id"]
    log(f"PASS: Created permission {perm_id}")
    
    # 2. Read Permission
    log("READ: GET /permissions/<id>")
    r = requests.get(f"{BASE_URL}/permissions/{perm_id}", headers=headers)
    if r.status_code != 200:
        log(f"FAIL: {r.status_code} {r.text}")
        return
    data = r.json()["data"]
    if data["permission_name"] == "Cert Test API Permission":
        log("PASS: Read successfully")
    else:
        log("FAIL: Data mismatch")
        
    # 3. Update Permission
    log("UPDATE: PUT /permissions/<id>")
    update_payload = {
        "permission_code": "CERT_TEST_API_PERM",
        "permission_name": "Cert Test API Permission Updated",
        "description": "Updated desc",
        "action": "execute",
        "status": "active"
    }
    r = requests.put(f"{BASE_URL}/permissions/{perm_id}", headers=headers, json=update_payload)
    if r.status_code != 200:
        log(f"FAIL: {r.status_code} {r.text}")
        return
    if r.json()["data"]["permission_name"] == "Cert Test API Permission Updated":
        log("PASS: Updated successfully")
    else:
        log("FAIL: Update mismatch")
        
    # 4. Check Audit logs via DB (to verify if anything was logged despite not seeing it in service)
    conn = psycopg2.connect('postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db')
    cur = conn.cursor()
    cur.execute("SELECT action, resource_type, resource_id FROM audit_logs ORDER BY timestamp DESC LIMIT 3")
    recent_logs = cur.fetchall()
    log("Recent Audit Logs:")
    for log_entry in recent_logs:
        log(f"  {log_entry}")
    
    # 5. Delete Permission
    log("DELETE: DELETE /permissions/<id>")
    r = requests.delete(f"{BASE_URL}/permissions/{perm_id}", headers=headers)
    if r.status_code == 200:
        log("PASS: Deleted successfully")
    else:
        log(f"FAIL: {r.status_code} {r.text}")
        
    # 6. Verify Deletion in DB
    cur.execute("SELECT count(*) FROM permissions WHERE id = %s", (perm_id,))
    count = cur.fetchone()[0]
    if count == 0:
        log("PASS: Hard delete confirmed in Database")
    else:
        log("FAIL: Record still exists in DB (Soft delete or not deleted)")
        
    conn.close()

if __name__ == "__main__":
    main()
