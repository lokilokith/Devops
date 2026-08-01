import json
import urllib.request
import urllib.error

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

print('--- Get First User ---')
status, body = request('GET', '/users?limit=1', None, headers)
user_id = body['data'][0]['id']
print('User ID:', user_id)

print('--- Get Help Desk Role ---')
status, body = request('GET', '/roles?search=HELP_DESK&limit=1', None, headers)
role_id = body['data'][0]['id']
print('Role ID:', role_id)

print('--- Get First Permission ---')
status, body = request('GET', '/permissions?limit=1', None, headers)
permission_id = body['data'][0]['id']
print('Permission ID:', permission_id)

print('1. Assign Role to User')
status, body = request('POST', f'/users/{user_id}/roles', {'role_id': role_id}, headers)
print(status, body)

print('2. Verify User Roles')
status, body = request('GET', f'/users/{user_id}/roles', None, headers)
print(status, body)

print('3. Remove Role from User')
status, body = request('DELETE', f'/users/{user_id}/roles/{role_id}', None, headers)
print(status, body)

print('4. Assign Permission to Role')
status, body = request('POST', f'/roles/{role_id}/permissions', {'permission_id': permission_id}, headers)
print(status, body)

print('5. Verify Role Permissions')
status, body = request('GET', f'/roles/{role_id}/permissions', None, headers)
print(status, body)

print('6. Remove Permission from Role')
status, body = request('DELETE', f'/roles/{role_id}/permissions/{permission_id}', None, headers)
print(status, body)


