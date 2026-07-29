import os
from sqlalchemy import select

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite:///opsforge.db'
os.environ['SECRET_KEY'] = 'test'

from app import create_app
import json
import urllib.request
import urllib.error

# 2. Login
url = 'http://127.0.0.1:5001/auth/login'
data = json.dumps({'username': 'admin', 'password': 'password'}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

try:
    response = urllib.request.urlopen(req)
    res_data = json.loads(response.read().decode())
    token = res_data['data']['access_token']
    
    # 3. Get /roles
    roles_url = 'http://127.0.0.1:5001/roles'
    roles_req = urllib.request.Request(roles_url, headers={'Authorization': f'Bearer {token}'})
    roles_response = urllib.request.urlopen(roles_req)
    print(json.dumps(json.loads(roles_response.read().decode()), indent=2))
    
except urllib.error.HTTPError as e:
    print('Error code:', e.code)
    print(e.read().decode())
except Exception as e:
    print('Exception:', e)
