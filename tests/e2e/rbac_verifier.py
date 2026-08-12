import requests
import sys

BASE_URL = "http://localhost/api/v1"
ADMIN_CREDS = {"username": "admin", "password": "secret123"}

def login():
    r = requests.post(f"{BASE_URL}/auth/login", json=ADMIN_CREDS)
    if r.status_code != 200:
        print("Login failed")
        sys.exit(1)
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}

def run_checks():
    headers = login()
    failures = 0
    
    def assert_check(condition, msg, r=None):
        nonlocal failures
        if not condition:
            err = f" - {r.text}" if r else ""
            print(f"FAIL: {msg}{err}")
            failures += 1
        else:
            print(f"PASS: {msg}")

    print("Verifying RBAC CRUD operations...")

    # Create Permission
    perm_payload = {
        "permission_code": "CERT_TEST_PERMISSION",
        "permission_name": "CERT_TEST_PERMISSION",
        "description": "Permission for certification test"
    }
    r = requests.post(f"{BASE_URL}/permissions", headers=headers, json=perm_payload)
    if r.status_code == 409: # Already exists from previous run, let's delete it
        pid = r.json().get('data', {}).get('id')
        if not pid:
            # Let's search for it
            r_all = requests.get(f"{BASE_URL}/permissions", headers=headers)
            for p in r_all.json()['data']['items'] if 'items' in r_all.json()['data'] else r_all.json()['data']:
                if p['permission_code'] == "CERT_TEST_PERMISSION":
                    pid = p['id']
                    break
        requests.delete(f"{BASE_URL}/permissions/{pid}", headers=headers)
        r = requests.post(f"{BASE_URL}/permissions", headers=headers, json=perm_payload)

    assert_check(r.status_code == 201, "Permission created (API CRUD C)", r)
    perm_id = r.json()['data']['id']

    # Read Permission
    r = requests.get(f"{BASE_URL}/permissions", headers=headers)
    perms = r.json()['data']['items'] if 'items' in r.json()['data'] else r.json()['data']
    found = any(p['id'] == perm_id for p in perms)
    assert_check(found, "Permission read (API CRUD R)", r)

    # Update Permission
    update_payload = {
        "permission_name": "CERT_TEST_PERMISSION_UPDATED",
        "description": "Updated certification permission",
        "action": "read",
        "status": "active"
    }
    r = requests.put(f"{BASE_URL}/permissions/{perm_id}", headers=headers, json=update_payload)
    assert_check(r.status_code == 200, "Permission updated (API CRUD U)", r)

    # Create Role
    role_payload = {
        "role_code": "CERT_TEST_ROLE",
        "role_name": "CERT_TEST_ROLE",
        "description": "Role for certification test"
    }
    r = requests.post(f"{BASE_URL}/roles", headers=headers, json=role_payload)
    if r.status_code == 409:
        # Search for it and delete
        r_all = requests.get(f"{BASE_URL}/roles", headers=headers)
        for rl in r_all.json()['data']['items'] if 'items' in r_all.json()['data'] else r_all.json()['data']:
            if rl['role_code'] == "CERT_TEST_ROLE":
                requests.delete(f"{BASE_URL}/roles/{rl['id']}", headers=headers)
                break
        r = requests.post(f"{BASE_URL}/roles", headers=headers, json=role_payload)
    assert_check(r.status_code == 201, "Role created (API CRUD C)", r)
    role_id = r.json()['data']['id']

    # Read Role
    r = requests.get(f"{BASE_URL}/roles", headers=headers)
    roles = r.json()['data']['items'] if 'items' in r.json()['data'] else r.json()['data']
    found = any(r_item['id'] == role_id for r_item in roles)
    assert_check(found, "Role read (API CRUD R)", r)

    # Update Role
    update_role = {
        "role_name": "CERT_TEST_ROLE_UPDATED",
        "description": "Updated certification role",
        "status": "active"
    }
    r = requests.put(f"{BASE_URL}/roles/{role_id}", headers=headers, json=update_role)
    assert_check(r.status_code == 200, "Role updated (API CRUD U)", r)

    # Assign permission to role
    r = requests.post(f"{BASE_URL}/roles/{role_id}/permissions", headers=headers, json={"permission_id": perm_id})
    assert_check(r.status_code in [201, 200], "Assigned permission to role", r)

    # Clean up (Delete)
    r = requests.delete(f"{BASE_URL}/roles/{role_id}/permissions/{perm_id}", headers=headers)
    assert_check(r.status_code in [200, 204], "Unassigned permission from role", r)

    r = requests.delete(f"{BASE_URL}/roles/{role_id}", headers=headers)
    assert_check(r.status_code in [200, 204], "Role deleted (API CRUD D)", r)

    r = requests.delete(f"{BASE_URL}/permissions/{perm_id}", headers=headers)
    assert_check(r.status_code in [200, 204], "Permission deleted (API CRUD D)", r)

    # Verify orphans
    r = requests.get(f"{BASE_URL}/roles", headers=headers)
    roles = r.json()['data']['items'] if 'items' in r.json()['data'] else r.json()['data']
    found = any(r_item['id'] == role_id for r_item in roles)
    assert_check(not found, "Verified role is completely deleted", r)
    
    r = requests.get(f"{BASE_URL}/permissions", headers=headers)
    perms = r.json()['data']['items'] if 'items' in r.json()['data'] else r.json()['data']
    found = any(p['id'] == perm_id for p in perms)
    assert_check(not found, "Verified permission is completely deleted", r)

    if failures > 0:
        print(f"RBAC Certification Failed with {failures} violations.")
        sys.exit(1)
    else:
        print("RBAC Certification Passed: 0 violations.")
        sys.exit(0)

if __name__ == "__main__":
    run_checks()
