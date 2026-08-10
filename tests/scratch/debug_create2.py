import requests
import psycopg2

BASE_URL = 'http://localhost/api/v1'

# Login as SEC_ADMIN
headers = {"Authorization": f"Bearer {requests.post(f'{BASE_URL}/auth/login', json={'username': 'admin', 'password': 'secret123'}).json()['data']['access_token']}"}

# Get users
users = requests.get(f"{BASE_URL}/users", headers=headers).json()['data']
sec_admin = next(u for u in users if u['username'].startswith('rbac_sec_admin'))

# login as sec_admin
headers_sec = {"Authorization": f"Bearer {requests.post(f'{BASE_URL}/auth/login', json={'username': sec_admin['username'], 'password': 'Password123!'}).json()['data']['access_token']}"}

res_id = requests.get(f"{BASE_URL}/resources", headers=headers).json()['data'][0]['id']

print("Sending CREATE request as SEC_ADMIN")
r = requests.post(f"{BASE_URL}/vault/secrets", headers=headers_sec, json={"resource_id": res_id, "payload": "test"})
print("Response:", r.status_code, r.text)

conn = psycopg2.connect('postgresql://opsforge:opsforge_pass@localhost:5432/opsforge_db')
cur = conn.cursor()
cur.execute("SELECT action FROM audit_logs ORDER BY timestamp DESC LIMIT 5")
print("Latest 5 Audit Logs:", cur.fetchall())
conn.close()
