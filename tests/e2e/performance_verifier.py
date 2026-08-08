import requests
import uuid
import sys
import time

BASE_URL = 'http://localhost:5000'

def login(username, password):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        return None
    token = r.json()['data']['access_token']
    return {"Authorization": f"Bearer {token}"}

def main():
    headers = login("admin", "secret123")
    if not headers:
        print("FAIL: Could not login as admin.")
        sys.exit(1)

    print("Running Performance Validation...")

    N = 100
    secrets = []
    
    start_time = time.time()
    
    # 1. Create N resources and secrets
    for i in range(N):
        res_id = requests.post(f"{BASE_URL}/resources", headers=headers, json={
            "resource_code": f"PERF_{uuid.uuid4().hex[:8].upper()}",
            "resource_name": f"Perf Test {uuid.uuid4().hex[:8]}",
            "description": "Perf test"
        }).json()['data']['id']

        r = requests.post(f"{BASE_URL}/vault/secrets", headers=headers, json={"resource_id": res_id, "payload": f"perf_payload_{i}"})
        assert r.status_code == 201
        secrets.append((res_id, r.json()['data']['id']))
    
    print(f"Created {N} secrets in {time.time() - start_time:.2f}s")
    
    # 2. Retrieve N secrets
    start_time = time.time()
    for res_id, sec_id in secrets:
        req = requests.post(f"{BASE_URL}/access-requests", headers=headers, json={"requested_resource_id": res_id, "business_justification": "Perf test retrieving secrets", "duration_hours": 1})
        req_id = req.json()['data']['id']
        requests.post(f"{BASE_URL}/access-requests/{req_id}/approve", headers=headers)
        r = requests.post(f"{BASE_URL}/vault/secrets/{sec_id}/retrieve", headers=headers, json={"reason": "perf retrieve"})
        assert r.status_code == 200, f"Retrieve failed: {r.status_code}"
    print(f"Retrieved {N} secrets (with Access Requests) in {time.time() - start_time:.2f}s")
    
    # 3. Rotate N secrets
    start_time = time.time()
    for i, (res_id, sec_id) in enumerate(secrets):
        r = requests.post(f"{BASE_URL}/vault/secrets/{sec_id}/rotate", headers=headers, json={"resource_id": res_id, "payload": f"perf_rotated_{i}"})
        assert r.status_code == 200
    print(f"Rotated {N} secrets in {time.time() - start_time:.2f}s")

    # 4. Disable N secrets
    start_time = time.time()
    for res_id, sec_id in secrets:
        r = requests.post(f"{BASE_URL}/vault/secrets/{sec_id}/disable", headers=headers, json={"resource_id": res_id})
        assert r.status_code == 200
    print(f"Disabled {N} secrets in {time.time() - start_time:.2f}s")

    # 5. List all secrets
    start_time = time.time()
    r = requests.get(f"{BASE_URL}/vault/secrets", headers=headers)
    assert r.status_code == 200
    print(f"Listed all secrets in {time.time() - start_time:.2f}s")

    # 6. Load dashboard stats
    start_time = time.time()
    r = requests.get(f"{BASE_URL}/vault/secrets/stats", headers=headers)
    assert r.status_code == 200, f"Stats failed: {r.status_code}"
    print(f"Loaded dashboard stats in {time.time() - start_time:.2f}s")
    
    print("Performance validation passed.")

if __name__ == '__main__':
    main()
