import urllib.request
import json
import urllib.error

req = urllib.request.Request("http://localhost:8000/auth/login", method="POST")
req.add_header('Content-Type', 'application/json')
req.data = json.dumps({"username": "admin", "password": "secret123"}).encode('utf-8')

try:
    with urllib.request.urlopen(req) as response:
        print("Status:", response.status)
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print("Status:", e.code)
    print(e.read().decode('utf-8'))
