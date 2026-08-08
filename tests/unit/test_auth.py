import sys
import json
import urllib.request
import urllib.error
import urllib.parse
from time import sleep

BASE_URL = 'http://localhost:5000'

def request(method, path, data=None, headers=None):
    if headers is None: headers = {}
    if data:
        data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))
    except Exception as e:
        print(f"Error: {e}")
        return 500, {}

print('--- Testing Login ---')
status, body = request('POST', '/auth/login', {'username': 'admin', 'password': 'secret123'})
if status == 401:
    print('Failed with secret123, trying admin/admin...')
    status, body = request('POST', '/auth/login', {'username': 'admin', 'password': 'admin'})
print(f"Login Status: {status}")
if status != 200: sys.exit(1)

access_token = body['data']['access_token']
refresh_token = body['data']['refresh_token']
headers = {'Authorization': f'Bearer {access_token}'}

print('--- Testing Session Restore (GET /auth/me) ---')
status, body = request('GET', '/auth/me', headers=headers)
print(f"/auth/me Status: {status}")
if status != 200: sys.exit(1)
print(f"User roles: {body['data']['roles']}")
print(f"User permissions count: {len(body['data'].get('permissions', []))}")

print('--- Testing JWT Refresh ---')
status, body = request('POST', '/auth/refresh', {'refresh_token': refresh_token})
print(f"Refresh Status: {status}")
if status != 200: sys.exit(1)
new_access = body['data']['access_token']

print('--- Testing Old Token (should be valid unless blacklisted, backend uses JWT stateless usually) ---')
status, body = request('GET', '/auth/me', headers={'Authorization': f'Bearer {access_token}'})
print(f"Old token Status (expect 200 or 401): {status}")

print('--- Testing New Token ---')
status, body = request('GET', '/auth/me', headers={'Authorization': f'Bearer {new_access}'})
print(f"New token Status: {status}")

print('--- Testing Logout ---')
status, body = request('POST', '/auth/logout', headers={'Authorization': f'Bearer {new_access}'})
print(f"Logout Status: {status}")

print('--- Testing Token After Logout ---')
status, body = request('GET', '/auth/me', headers={'Authorization': f'Bearer {new_access}'})
print(f"After logout Status (expect 401): {status}")




