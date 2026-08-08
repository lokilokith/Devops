import urllib.request
import json
import urllib.error

url = 'http://127.0.0.1:8000/auth/login'
data = json.dumps({'username': 'admin', 'password': 'password'}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

try:
    response = urllib.request.urlopen(req)
    print(response.read().decode())
except urllib.error.HTTPError as e:
    print('Error code:', e.code)
    print(e.read().decode())
except Exception as e:
    print('Exception:', e)
