import json
import urllib.request
import urllib.error
import uuid

BASE_URL = 'http://localhost:5000'
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'secret123'

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

print('--- Login ---')
status, body = request('POST', '/auth/login', {'username': ADMIN_USERNAME, 'password': ADMIN_PASSWORD})
if status != 200:
    print('Failed to login:', body)
    exit(1)
token = body['data']['access_token']
headers = {'Authorization': f'Bearer {token}'}

print('--- Testing Roles ---')
test_id = uuid.uuid4().hex[:8]
role_code = f'ROLE_{test_id.upper()}'

print('1. Create Role')
payload = {
    'role_code': role_code,
    'role_name': 'Test Role',
    'description': 'A test role',
    'role_type': 'custom'
}
status, body = request('POST', '/roles', payload, headers)
print(status, body)
if status not in (200, 201):
    exit(1)
role_id = body['data']['id']

print('2. Duplicate Role Validation')
status, body = request('POST', '/roles', payload, headers)
print(status, body)

print('3. Edit Role')
status, body = request('PUT', f'/roles/{role_id}', {'role_name': 'Updated Role'}, headers)
print(status, body)

print('4. Search and Pagination')
status, body = request('GET', f'/roles?search={role_code}&skip=0&limit=10', None, headers)
print(status, body)

print('5. Delete Role')
status, body = request('DELETE', f'/roles/{role_id}', None, headers)
print(status, body)

print('--- Testing Permissions ---')
print('1. List Permissions')
status, body = request('GET', '/permissions?skip=0&limit=5', None, headers)
print(status, body)


