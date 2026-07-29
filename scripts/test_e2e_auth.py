import urllib.request
import json
import urllib.error

BASE_URL = "http://127.0.0.1:5001"

def print_result(step, expected, actual, success):
    print(f"[{'PASS' if success else 'FAIL'}] {step} (Expected: {expected}, Actual: {actual})")

def do_req(method, path, data=None, token=None):
    req = urllib.request.Request(f"{BASE_URL}{path}", method=method)
    if data:
        req.add_header('Content-Type', 'application/json')
        req.data = json.dumps(data).encode('utf-8')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
        
    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            return response.status, json.loads(res_body) if res_body else None
    except urllib.error.HTTPError as e:
        res_body = e.read().decode('utf-8')
        return e.code, json.loads(res_body) if res_body else None
    except urllib.error.URLError as e:
        print("URL Error:", e)
        return 0, None

def main():
    print("=== E2E Authorization Test ===\n")
    
    # 1. Login as Admin
    status, data = do_req("POST", "/auth/login", {"username": "admin", "password": "secret123"})
    if status != 200:
        print("Failed to login as admin:", status, data)
        return
    admin_token = data["data"]["access_token"]
    print("1. Logged in as Admin")
    
    # 2. Create Limited User
    user_data = {
        "employee_id": "LTD002",
        "username": "lim_e2e_2",
        "email": "lim2@example.com",
        "full_name": "Limited User 2",
        "password": "password123"
    }
    status, data = do_req("POST", "/users", user_data, admin_token)
    
    if status == 201:
        user_id = data["data"]["id"]
    elif status == 409:
        status, data = do_req("GET", "/users", token=admin_token)
        users = data["data"]
        user_id = next(u["id"] for u in users if u["username"] == "lim_e2e_2")
    else:
        print("Failed to create user:", status, data)
        return
    print("2. Ensured limited user exists")

    # 3. Create Role Help Desk
    role_data = {
        "role_code": "HELP_DESK_2",
        "role_name": "Help Desk 2"
    }
    status, data = do_req("POST", "/roles", role_data, admin_token)
    if status == 201:
        role_id = data["data"]["id"]
    elif status == 409:
        status, data = do_req("GET", "/roles", token=admin_token)
        roles = data["data"]
        role_id = next(r["id"] for r in roles if r["role_code"] == "HELP_DESK_2")
    else:
        print("Failed to create role:", status, data)
        return
    print("3. Ensured HELP_DESK_2 role exists")
    
    # 4. Find users.read permission
    status, data = do_req("GET", "/permissions", token=admin_token)
    permissions = data["data"]
    perm_id = next((p["id"] for p in permissions if p["permission_name"] == "users.read"), None)
    if not perm_id:
        print("users.read permission not found. Are RBAC seeds run?")
        return
    
    # 5. Assign permission to role
    do_req("POST", f"/roles/{role_id}/permissions", {"permission_id": perm_id}, admin_token)
    print("4. Assigned users.read to HELP_DESK_2 role")
    
    # 6. Assign role to user
    status, data = do_req("POST", f"/users/{user_id}/roles", {"role_id": role_id}, admin_token)
    print("5. Assigned HELP_DESK_2 role to limited user. Status:", status, data)
    
    # 7. Login as Limited User
    status, data = do_req("POST", "/auth/login", {"username": "lim_e2e_2", "password": "password123"})
    if status != 200:
        print("Failed to login as limited user:", status, data)
        return
    lim_token = data["data"]["access_token"]
    print("6. Logged in as Limited User\n")
    
    # Check 0: GET /auth/me to see roles and permissions
    status, data = do_req("GET", "/auth/me", token=lim_token)
    print("GET /auth/me:", data)
    
    print("--- Executing Authorization Checks ---")
    # Check 1: GET /users (Allowed)
    status, _ = do_req("GET", "/users", token=lim_token)
    print_result("GET /users", 200, status, status == 200)
    
    # Check 2: POST /users (Forbidden)
    status, _ = do_req("POST", "/users", {"employee_id": "t", "username": "t", "email": "t@t.com", "full_name": "T"}, token=lim_token)
    print_result("POST /users", 403, status, status == 403)
    
    # Check 3: GET /roles (Forbidden)
    status, _ = do_req("GET", "/roles", token=lim_token)
    print_result("GET /roles", 403, status, status == 403)

if __name__ == "__main__":
    main()
