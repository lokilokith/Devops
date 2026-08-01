import requests
import time
import json
import uuid

BASE_URL = 'http://localhost:5000/api/v1'

def print_step(msg):
    print(f"\n{'='*50}\n[STEP] {msg}\n{'='*50}")

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        print(f"Login failed for {username}: {r.text}")
        return None
    token = r.json()['data']['access_token']
    return {"Authorization": f"Bearer {token}"}

def main():
    print_step("Administrator Login")
    admin_headers = login("admin", "admin") # default admin credentials
    if not admin_headers:
        print("Could not login as admin. Check credentials or if DB is seeded.")
        return

    # test users endpoint
    r = requests.get(f"{BASE_URL}/users", headers=admin_headers)
    print(f"GET /users: {r.status_code}")
    
    # 2. Create new role
    print_step("Create new role")
    role_name = f"TestRole_{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{BASE_URL}/roles", headers=admin_headers, json={
        "role_name": role_name,
        "description": "A test role"
    })
    print(f"Create Role: {r.status_code} - {r.text}")
    if r.status_code not in (200, 201):
        return
    role_id = r.json()['data']['id']

    # 3. Assign permissions
    print_step("Assign permissions to role")
    # First get permissions
    r = requests.get(f"{BASE_URL}/permissions", headers=admin_headers)
    perms = r.json().get('data', {}).get('items', [])
    if not perms:
        print("No permissions found to assign!")
    else:
        # Assign first permission
        perm_id = perms[0]['id']
        r = requests.post(f"{BASE_URL}/roles/{role_id}/permissions", headers=admin_headers, json={"permission_ids": [perm_id]})
        print(f"Assign Permission: {r.status_code} - {r.text}")

    # 4. Create new user
    print_step("Create new user")
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{BASE_URL}/users", headers=admin_headers, json={
        "username": username,
        "email": f"{username}@example.com",
        "full_name": "Test User",
        "password": "Password123!"
    })
    print(f"Create User: {r.status_code} - {r.text}")
    if r.status_code not in (200, 201):
        return
    user_id = r.json()['data']['id']

    # 5. Assign role to user
    print_step("Assign role to user")
    r = requests.post(f"{BASE_URL}/users/{user_id}/roles", headers=admin_headers, json={"role_ids": [role_id]})
    print(f"Assign Role to User: {r.status_code} - {r.text}")

    # 6 & 7. Login as new user
    print_step("Login as new user")
    user_headers = login(username, "Password123!")
    if not user_headers:
        return
    
    # 8. Submit access request
    print_step("Submit access request")
    # need a resource to request
    r = requests.get(f"{BASE_URL}/resources", headers=admin_headers)
    resources = r.json().get('data', {}).get('items', [])
    if not resources:
        # Create a resource
        r = requests.post(f"{BASE_URL}/resources", headers=admin_headers, json={
            "resource_code": f"RES_{uuid.uuid4().hex[:4]}",
            "resource_name": "Test Resource",
            "description": "Test"
        })
        res_id = r.json()['data']['id']
    else:
        res_id = resources[0]['id']

    r = requests.post(f"{BASE_URL}/access-requests", headers=user_headers, json={
        "resource_id": res_id,
        "justification": "Need access for testing",
        "duration_hours": 24
    })
    print(f"Create Request: {r.status_code} - {r.text}")
    if r.status_code not in (200, 201):
        return
    req_id = r.json()['data']['id']

    # 11 & 12. Login as approver (admin)
    print_step("Check approval queue")
    r = requests.get(f"{BASE_URL}/approval-workflows?status=pending", headers=admin_headers)
    print(f"Approval Queue: {r.status_code} - {r.text}")

    # 13. Approve request
    print_step("Approve request")
    r = requests.post(f"{BASE_URL}/access-requests/{req_id}/approve", headers=admin_headers, json={"comments": "Approved for testing"})
    print(f"Approve Request: {r.status_code} - {r.text}")

if __name__ == '__main__':
    main()
