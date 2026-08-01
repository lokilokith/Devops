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

print('--- Testing Users ---')
test_id = uuid.uuid4().hex[:8]
username = f'testuser_{test_id}'
email = f'test_{test_id}@example.com'
emp_id = f'EMP_{test_id}'

print('1. Create User')
payload = {
    'username': username,
    'email': email,
    'full_name': 'Test User',
    'employee_id': emp_id,
    'password': 'Password123!'
}
status, body = request('POST', '/users', payload, headers)
print(status, body)
user_id = body['data']['id']

print('4. Edit User')
status, body = request('PUT', f'/users/{user_id}', {'full_name': 'Updated Name', 'status': 'active'}, headers)
print(status, body)

print('7. Search and Pagination')
status, body = request('GET', f'/users?search={username}&page=1&size=10', None, headers)
print(status, body)

print('8. Delete User')
status, body = request('DELETE', f'/users/{user_id}', None, headers)
print(status, body)
