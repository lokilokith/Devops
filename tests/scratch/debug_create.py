import requests
import json
BASE_URL = 'http://localhost/api/v1'

def run():
    # Login as SEC_ADMIN
    headers = {"Authorization": f"Bearer {requests.post(f'{BASE_URL}/auth/login', json={'username': 'rbac_sec_admin_3b99', 'password': 'Password123!'}).json()['data']['access_token']}"}
    
    # Try create
    res_id = requests.get(f"{BASE_URL}/resources", headers={"Authorization": f"Bearer {requests.post(f'{BASE_URL}/auth/login', json={'username': 'admin', 'password': 'secret123'}).json()['data']['access_token']}"}).json()['data'][0]['id']
    
    r = requests.post(f"{BASE_URL}/vault/secrets", headers=headers, json={"resource_id": res_id, "payload": "test"})
    print("CREATE:", r.status_code, r.text)
    
if __name__ == "__main__":
    run()
