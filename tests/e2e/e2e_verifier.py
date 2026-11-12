import time

import psycopg2
import requests

BASE_URL = "http://localhost/api/v1"


def login(username, password):
    resp = requests.post(
        f"{BASE_URL}/auth/login", json={"username": username, "password": password}
    )
    if resp.status_code != 200:
        print(f"Login failed for {username}: {resp.json()}")
        return None
    return resp.json()["data"]["access_token"]


def get_headers(token):
    return {"Authorization": f"Bearer {token}"}


def run_users_workflow(token):
    print("--- RUNNING USERS WORKFLOW ---")
    headers = get_headers(token)

    # 1. Create a new user
    username = "test_user_e2e"
    payload = {
        "employee_id": "E2E001",
        "username": username,
        "email": "e2e@example.com",
        "full_name": "E2E Test User",
        "password": "Password123!",
    }

    # Delete if exists from previous run
    print("Checking if user exists and deleting...")
    resp = requests.get(
        f"{BASE_URL}/users", headers=headers, params={"search": username}
    )
    if resp.json()["data"]:
        for u in resp.json()["data"]:
            requests.delete(f"{BASE_URL}/users/{u['id']}", headers=headers)
            print(f"Deleted old {u['username']}")

    print("Creating user...")
    resp = requests.post(f"{BASE_URL}/users", headers=headers, json=payload)
    assert resp.status_code == 201, f"Create failed: {resp.json()}"
    user_id = resp.json()["data"]["id"]
    print(f"[SUCCESS] Created User: {user_id}")

    # 2. Edit User
    print("Editing user...")
    edit_payload = {
        "email": "e2e@example.com",
        "full_name": "E2E Test User Edited",
        "status": "active",
    }
    resp = requests.put(
        f"{BASE_URL}/users/{user_id}", headers=headers, json=edit_payload
    )
    assert resp.status_code == 200, f"Edit failed: {resp.json()}"
    assert resp.json()["data"]["full_name"] == "E2E Test User Edited"
    print("[SUCCESS] Edited User")

    # 3. Disable User
    print("Disabling user...")
    disable_payload = {**edit_payload, "status": "disabled"}
    resp = requests.put(
        f"{BASE_URL}/users/{user_id}", headers=headers, json=disable_payload
    )
    assert resp.status_code == 200, f"Disable failed: {resp.json()}"
    assert resp.json()["data"]["status"] == "disabled"
    print("[SUCCESS] Disabled User")

    # 4. Enable User
    print("Enabling user...")
    enable_payload = {**edit_payload, "status": "active"}
    resp = requests.put(
        f"{BASE_URL}/users/{user_id}", headers=headers, json=enable_payload
    )
    assert resp.status_code == 200, f"Enable failed: {resp.json()}"
    assert resp.json()["data"]["status"] == "active"
    print("[SUCCESS] Enabled User")

    # 5. Delete and Recreate 5x
    print("Running Delete/Recreate 5x workflow...")
    # Delete the one we just made
    resp = requests.delete(f"{BASE_URL}/users/{user_id}", headers=headers)
    assert resp.status_code == 200, f"Delete failed: {resp.json()}"

    for i in range(5):
        # Create
        resp = requests.post(f"{BASE_URL}/users", headers=headers, json=payload)
        assert resp.status_code == 201, f"Create {i} failed: {resp.json()}"
        uid = resp.json()["data"]["id"]

        # Delete
        resp = requests.delete(f"{BASE_URL}/users/{uid}", headers=headers)
        assert resp.status_code == 200, f"Delete {i} failed: {resp.json()}"
    print("[SUCCESS] 5x Recreate/Delete successful")

    # 6. Search & Pagination
    print("Checking Search & Pagination...")
    requests.post(
        f"{BASE_URL}/users", headers=headers, json=payload
    )  # leave one active
    resp = requests.get(
        f"{BASE_URL}/users",
        headers=headers,
        params={"search": "E2E", "limit": 1, "skip": 0},
    )
    assert resp.status_code == 200, f"Search failed: {resp.json()}"
    assert len(resp.json()["data"]) == 1
    print("[SUCCESS] Search and Pagination successful")


def run_access_request_workflow(admin_token):
    print("--- RUNNING ACCESS REQUESTS WORKFLOW ---")
    headers = get_headers(admin_token)

    # Create a normal user
    print("Creating requester user...")
    user_payload = {
        "employee_id": "REQ001",
        "username": "requester",
        "email": "req@example.com",
        "full_name": "Requester User",
        "password": "Password123!",
    }
    # Clean up old requester if exists
    resp = requests.get(
        f"{BASE_URL}/users", headers=headers, params={"search": "requester"}
    )
    if resp.json()["data"]:
        for u in resp.json()["data"]:
            requests.delete(f"{BASE_URL}/users/{u['id']}", headers=headers)

    requests.post(f"{BASE_URL}/users", headers=headers, json=user_payload)
    req_token = login("requester", "Password123!")
    req_headers = get_headers(req_token)

    # Get a role to request
    roles_resp = requests.get(f"{BASE_URL}/roles", headers=headers)
    role_id = roles_resp.json()["data"][0]["id"]

    # 1. Create access request
    print("Creating access request...")
    ar_payload = {
        "business_justification": "Need access to this role for testing e2e",
        "requested_role_id": role_id,
        "priority": "high",
    }
    resp = requests.post(
        f"{BASE_URL}/access-requests", headers=req_headers, json=ar_payload
    )
    assert resp.status_code == 201, f"Failed to create AR: {resp.json()}"
    ar_id1 = resp.json()["data"]["id"]
    print("[SUCCESS] Created Access Request 1")

    # 2. Cancel access request
    print("Cancelling access request...")
    resp = requests.post(
        f"{BASE_URL}/access-requests/{ar_id1}/cancel", headers=req_headers
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "cancelled"
    print("[SUCCESS] Cancelled Access Request 1")

    # 3. Create another one for approval
    resp = requests.post(
        f"{BASE_URL}/access-requests", headers=req_headers, json=ar_payload
    )
    ar_id2 = resp.json()["data"]["id"]
    print("[SUCCESS] Created Access Request 2 for Approval")

    # 4. Search & Filter (as requester)
    print("Searching access requests...")
    resp = requests.get(
        f"{BASE_URL}/access-requests",
        headers=req_headers,
        params={"search": "e2e", "status": "pending"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 1
    print("[SUCCESS] Search and Filter successful")

    # 5. Approval Workflow (as admin)
    print("Admin finding pending workflow...")
    # Give it a moment to create the workflow via background or sync
    time.sleep(1)
    aw_resp = requests.get(
        f"{BASE_URL}/approval-workflows", headers=headers, params={"status": "pending"}
    )
    aw = None
    for w in aw_resp.json()["data"]:
        if w["access_request_id"] == ar_id2:
            aw = w
            break
    assert aw is not None, "Pending workflow not found"

    print("Admin approving workflow...")
    resp = requests.post(
        f"{BASE_URL}/approval-workflows/{aw['id']}/approve",
        headers=headers,
        json={"comments": "Approved for e2e"},
    )
    assert resp.status_code == 200, f"Approve failed: {resp.json()}"
    print("[SUCCESS] Approved Access Request 2")

    # Verify AR is approved
    ar_resp = requests.get(f"{BASE_URL}/access-requests/{ar_id2}", headers=headers)
    assert ar_resp.json()["data"]["status"] == "approved"
    print("[SUCCESS] Status updated to Approved")

    # Create another to reject
    resp = requests.post(
        f"{BASE_URL}/access-requests", headers=req_headers, json=ar_payload
    )
    ar_id3 = resp.json()["data"]["id"]

    aw_resp = requests.get(
        f"{BASE_URL}/approval-workflows", headers=headers, params={"status": "pending"}
    )
    aw = [w for w in aw_resp.json()["data"] if w["access_request_id"] == ar_id3][0]

    print("Admin rejecting workflow...")
    resp = requests.post(
        f"{BASE_URL}/approval-workflows/{aw['id']}/reject",
        headers=headers,
        json={"comments": "Rejected for e2e"},
    )
    assert resp.status_code == 200

    ar_resp = requests.get(f"{BASE_URL}/access-requests/{ar_id3}", headers=headers)
    assert ar_resp.json()["data"]["status"] == "rejected"
    assert ar_resp.json()["data"]["rejected_reason"] == "Rejected for e2e"
    print("[SUCCESS] Rejected Access Request 3")


def run_db_validation():
    print("--- RUNNING DB VALIDATION ---")
    conn = psycopg2.connect(
        dbname="opsforge_db",
        user="opsforge",
        password="opsforge_pass",
        host="localhost",
    )
    cur = conn.cursor()

    print("Checking duplicate users issue...")
    cur.execute("SELECT username, status FROM users WHERE username = 'test_user_e2e'")
    users = cur.fetchall()
    active_users = [u for u in users if u[1] == "active"]
    assert (
        len(active_users) <= 1
    ), f"Found multiple active users with same username: {active_users}"
    print("[SUCCESS] DB: No duplicate active users")

    print("Checking access_requests status...")
    cur.execute(
        "SELECT status FROM access_requests WHERE business_justification LIKE '%e2e%'"
    )
    statuses = [s[0] for s in cur.fetchall()]
    assert all(s in ["pending", "approved", "rejected", "cancelled"] for s in statuses)
    print("[SUCCESS] DB: Access requests have valid statuses")

    conn.close()


if __name__ == "__main__":
    print("Waiting for API to be ready...")
    time.sleep(5)

    admin_token = login("admin", "secret123")
    if not admin_token:
        print("Could not login as admin. Is the seed data loaded?")
        exit(1)

    try:
        run_users_workflow(admin_token)
        run_access_request_workflow(admin_token)
        run_db_validation()
        print("\n\n[SUCCESS] ALL E2E VERIFICATIONS PASSED!")
    except AssertionError as e:
        print(f"\n[ERROR] E2E VERIFICATION FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n[ERROR] UNEXPECTED ERROR: {e}")
        exit(1)
