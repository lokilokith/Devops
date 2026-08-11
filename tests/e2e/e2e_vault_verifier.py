import requests
import json
import uuid
import sys
import time

BASE_URL = 'http://localhost:5000'

def print_step(msg):
    print(f"\n{'='*50}\n[STEP] {msg}\n{'='*50}")

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        return None
    token = r.json()['data']['access_token']
    return {"Authorization": f"Bearer {token}"}

def verify_audit_log(headers, resource_id, expected_action, actor_id=None, resource_type="vault_secrets"):
    time.sleep(1) # Wait for db flush
    r = requests.get(f"{BASE_URL}/audit?resource_type={resource_type}", headers=headers)
    logs = r.json().get('data', {}).get('items', [])
    print(f"DEBUG Audit Logs length: {len(logs)}. Searching for resource: {resource_id} action: {expected_action}")
    for log in logs:
        if log['resource_id'] == resource_id and log['action'] == expected_action:
            if actor_id and log.get('user_id') != actor_id:
                print(f"DEBUG: actor_id mismatch! Expected {actor_id}, got log: {log}")
                import subprocess
                out = subprocess.check_output(
                    ['psql', '-U', 'postgres', '-d', 'opsforge', '-c', f"SELECT id, action, actor_user_id FROM audit_logs WHERE resource_id = '{resource_id}'"],
                    text=True
                )
                print(f"DB AUDIT LOGS:\n{out}")
                continue
            return True
    print(f"DEBUG: missing audit log. Found logs: {[ (l['resource_id'], l['action']) for l in logs ]}")
    return False

def verify_api_contract_list(resp_data):
    # GET /vault/secrets Returns only metadata. Must never return encrypted_payload, encrypted_dek, nonce, plaintext
    if isinstance(resp_data, list):
        for item in resp_data:
            keys = item.keys()
            for bad_key in ['encrypted_payload', 'encrypted_dek', 'nonce', 'payload', 'plaintext']:
                if bad_key in keys:
                    return False
    return True

def verify_api_contract_stats(resp_data):
    keys = resp_data.keys()
    if 'total_secrets' not in keys or 'active_secrets' not in keys or 'disabled_secrets' not in keys:
        return False
    return True

def main():
    admin_headers = login("admin", "secret123")
    if not admin_headers:
        print("FAIL: Could not login as admin.")
        sys.exit(1)
        
    print_step("Get Admin User ID")
    r = requests.get(f"{BASE_URL}/auth/me", headers=admin_headers)
    admin_id = r.json()['data']['id']

    # 1. API Contract & Workflow: Create -> Retrieve -> Rotate -> Disable
    print_step("E2E Scenario 1: Create, Retrieve, Rotate, Disable, Audit")
    
    # Need a resource to attach secret
    r = requests.post(f"{BASE_URL}/resources", headers=admin_headers, json={
        "resource_code": f"RES_VAULT_{uuid.uuid4().hex[:4].upper()}",
        "resource_name": f"Vault Test Resource {uuid.uuid4().hex[:4]}",
        "description": "Test"
    })
    if r.status_code != 201:
        print("Create resource failed:", r.status_code, r.text)
    res_id = r.json()['data']['id']
    
    # Create Secret
    payload = "my_super_secret"
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json={"resource_id": res_id, "payload": payload})
    # print("Secret creation response:", r.json())
    assert r.status_code == 201, f"Failed to create secret: {r.text}"
    secret_id = r.json()['data']['id']
    assert verify_api_contract_list([r.json()['data']]), "API Contract violation on CREATE (leaked payload)"
    
    assert verify_audit_log(admin_headers, secret_id, "SECRET_CREATED"), "Audit log SECRET_CREATED missing"

    # Submit Access Request
    print_step("Submit Access Request for Secret Retrieval")
    r = requests.post(f"{BASE_URL}/access-requests", headers=admin_headers, json={
        "business_justification": "Need to retrieve vault secret for E2E testing",
        "requested_resource_id": res_id
    })
    assert r.status_code == 201, f"Failed to create access request: {r.status_code} {r.text}"
    req_id = r.json()['data']['id']
    
    # Approve Access Request
    print_step("Approve Access Request")
    r = requests.post(f"{BASE_URL}/access-requests/{req_id}/approve", headers=admin_headers)
    assert r.status_code == 200, f"Failed to approve access request: {r.status_code} {r.text}"
    
    # Retrieve Secret
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=admin_headers)
    assert r.status_code == 200, f"Failed to retrieve secret: {r.status_code} {r.text}"
    assert r.json()['data']['payload'] == payload, "Plaintext mismatch"
    
    assert verify_audit_log(admin_headers, secret_id, "SECRET_RETRIEVED"), "Audit log SECRET_RETRIEVED missing"
    
    # Rotate Secret
    new_payload = "rotated_secret"
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/rotate", headers=admin_headers, json={"payload": new_payload, "resource_id": res_id})
    assert r.status_code == 200, f"Failed to rotate secret: {r.status_code} {r.text}"
    
    assert verify_audit_log(admin_headers, secret_id, "SECRET_ROTATED"), "Audit log SECRET_ROTATED missing"
    
    # Retrieve Rotated
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/retrieve", headers=admin_headers)
    assert r.json()['data']['payload'] == new_payload, "Rotated plaintext mismatch"
    
    # Disable Secret
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id}/disable", headers=admin_headers)
    assert r.status_code == 200, "Failed to disable secret"
    
    assert verify_audit_log(admin_headers, secret_id, "SECRET_DISABLED"), "Audit log SECRET_DISABLED missing"

    print_step("Vault Stats Contract")
    r = requests.get(f"{BASE_URL}/vault/secrets/stats", headers=admin_headers)
    assert r.status_code == 200
    assert verify_api_contract_stats(r.json()['data']), "API Contract violation on STATS"
    print("Total Secrets:", r.json()['data']['total_secrets'])

    print_step("RBAC & Unauthorized Retrieval")
    
    # Create SOC Analyst role and user
    soc_user = f"soc_{uuid.uuid4().hex[:4]}"
    soc_pass = "Password123!"
    r = requests.post(f"{BASE_URL}/users", headers=admin_headers, json={
        "username": soc_user, "email": f"{soc_user}@example.com", "full_name": "SOC", "password": soc_pass, "employee_id": f"EMP_{uuid.uuid4().hex[:6].upper()}"
    })
    if r.status_code != 201:
        print("Create user failed:", r.status_code, r.text)
    soc_user_id = r.json()['data']['id']
    
    # Need to find or create SOC Analyst role
    r = requests.get(f"{BASE_URL}/roles", headers=admin_headers)
    soc_role_id = next((role['id'] for role in r.json()['data'] if 'SOC' in role['role_name']), None)
    if not soc_role_id:
        r = requests.post(f"{BASE_URL}/roles", headers=admin_headers, json={"role_name": "SOC Analyst", "role_code": f"SOC_{uuid.uuid4().hex[:4].upper()}"})
        soc_role_id = r.json()['data']['id']
        
    r = requests.post(f"{BASE_URL}/users/{soc_user_id}/roles", headers=admin_headers, json={"role_id": soc_role_id})
    if r.status_code != 201 and "already assigned" not in r.text:
        print("Failed to assign role to SOC user:", r.status_code, r.text)
    
    # Negative API Test: Assign an INACTIVE permission
    print_step("Permission Negative API Test")
    
    # 1. Get the PERM_VAULT_READ permission ID
    r = requests.get(f"{BASE_URL}/permissions?search=PERM_VAULT_READ", headers=admin_headers)
    perms = [p for p in r.json().get('data', []) if p['permission_code'] == 'PERM_VAULT_READ']
    assert len(perms) > 0, "PERM_VAULT_READ not found in system"
    perm_id = perms[0]['id']
    
    # 2. Assign PERM_VAULT_READ to SOC Analyst role
    r = requests.post(f"{BASE_URL}/roles/{soc_role_id}/permissions", headers=admin_headers, json={"permission_id": perm_id})
    if r.status_code != 201 and "already assigned" not in r.text:
        print("Failed to assign permission:", r.status_code, r.text)
    
    # 3. Patch permission to INACTIVE
    r = requests.patch(f"{BASE_URL}/permissions/{perm_id}", headers=admin_headers, json={"status": "inactive"})
    assert r.status_code == 200, f"Failed to patch permission to inactive: {r.status_code} {r.text}"
    
    # Create a new secret for SOC test since the previous one was disabled
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json={"resource_id": res_id, "payload": "soc_test_payload"})
    assert r.status_code == 201, "Failed to create secret for SOC test"
    soc_secret_id = r.json()['data']['id']

    soc_headers = login(soc_user, soc_pass)
    # 4. Attempt retrieve -> Expected 403 Forbidden
    r = requests.post(f"{BASE_URL}/vault/secrets/{soc_secret_id}/retrieve", headers=soc_headers)
    print("SOC Retrieve Status (with INACTIVE perm):", r.status_code)
    assert r.status_code == 403, f"Expected 403 Forbidden because permission is INACTIVE, got {r.status_code}"
    
    # Restore permission to ACTIVE
    r = requests.patch(f"{BASE_URL}/permissions/{perm_id}", headers=admin_headers, json={"status": "active"})
    assert r.status_code == 200

    print_step("Approval Workflow Validation")
    # Now the SOC user has ACTIVE PERM_VAULT_READ.
    # Create ResourceAccessPolicy requiring approval for this resource
    r = requests.post(f"{BASE_URL}/resources", headers=admin_headers, json={
        "resource_code": f"RES_VAULT_{uuid.uuid4().hex[:4].upper()}",
        "resource_name": f"Vault Test Resource {uuid.uuid4().hex[:4]}",
        "description": "Test"
    })
    res_id_2 = r.json()['data']['id']

    # Create Secret 2
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=admin_headers, json={"resource_id": res_id_2, "payload": "secret_2_payload"})
    secret_id_2 = r.json()['data']['id']

    # The ResourceAccessPolicy API does not exist yet in Phase 1, so we insert it directly via SQLAlchemy
    from app import create_app
    from app.platform.extensions import db
    from app.resources.models import ResourceAccessPolicy

    app = create_app()
    with app.app_context():
        policy = ResourceAccessPolicy(
            id=uuid.uuid4(),
            resource_id=uuid.UUID(res_id_2),
            role_id=uuid.UUID(soc_role_id),
            approval_required=True
        )
        db.session.add(policy)
        db.session.commit()

    # SOC tries to retrieve -> Should be 403 APPROVAL_REQUIRED
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id_2}/retrieve", headers=soc_headers)
    assert r.status_code == 403, f"Expected 403 APPROVAL_REQUIRED, got {r.status_code}"
    assert r.json().get('error') == 'APPROVAL_REQUIRED', f"Expected APPROVAL_REQUIRED error, got {r.json()}"

    # SOC Creates Access Request
    r = requests.post(f"{BASE_URL}/access-requests", headers=soc_headers, json={
        "business_justification": "Need access for SOC duties",
        "requested_resource_id": res_id_2
    })
    assert r.status_code == 201, "Failed to create access request"
    soc_req_id = r.json()['data']['id']

    # Admin Approves
    r = requests.post(f"{BASE_URL}/access-requests/{soc_req_id}/approve", headers=admin_headers)
    assert r.status_code == 200, "Failed to approve access request"

    # SOC Retrieves successfully
    r = requests.post(f"{BASE_URL}/vault/secrets/{secret_id_2}/retrieve", headers=soc_headers)
    assert r.status_code == 200, f"SOC Analyst should retrieve secret successfully after approval, got {r.status_code} {r.text}"
    assert r.json()['data']['payload'] == "secret_2_payload", "Decrypted payload mismatch"
           
    print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == '__main__':
    main()
