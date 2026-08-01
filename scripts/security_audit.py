import os
import sys
import json
import uuid
import datetime

os.environ["APP_ENV"] = "testing"
os.environ["SECRET_KEY"] = "super-secret-default-key-at-least-32-bytes"

from app import create_app
from app.extensions import db
from app.auth.service import AuthService
from app.identity.repository import IdentityRepository
from app.identity.models import User
from app.roles.models import Role, UserRole
from app.security.bootstrap import seed_rbac

def run_audit():
    app = create_app()
    with app.app_context():
        db.create_all()
        seed_rbac()
        
        auth_svc = AuthService(IdentityRepository(db.session))
        
        admin = db.session.query(User).filter_by(username="admin").first()
        if not admin:
            admin = User(employee_id="ADMIN1", username="admin", email="a@a.com", full_name="Admin")
            admin.password_hash = auth_svc.hash_password("secret")
            db.session.add(admin)
            admin_role = db.session.query(Role).filter_by(role_code="ADMIN").first()
            if admin_role:
                db.session.add(UserRole(user_id=admin.id, role_id=admin_role.id))
            db.session.commit()
            
        user_a = db.session.query(User).filter_by(username="user_a").first()
        if not user_a:
            user_a = User(employee_id="USRA", username="user_a", email="a@ops.local", full_name="User A")
            user_a.password_hash = auth_svc.hash_password("secret")
            db.session.add(user_a)
            db.session.commit()
            
        user_b = db.session.query(User).filter_by(username="user_b").first()
        if not user_b:
            user_b = User(employee_id="USRB", username="user_b", email="b@ops.local", full_name="User B")
            user_b.password_hash = auth_svc.hash_password("secret")
            db.session.add(user_b)
            db.session.commit()

        admin_token = auth_svc.generate_access_token(admin.id)
        user_a_token = auth_svc.generate_access_token(user_a.id)
        user_b_token = auth_svc.generate_access_token(user_b.id)

        client = app.test_client()
        results = []

        def log_test(phase, name, request_info, expected, actual, passed, evidence):
            results.append({
                "phase": phase,
                "name": name,
                "request": request_info,
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "evidence": evidence
            })

        # B. Authentication
        resp = client.get("/users", headers={"Authorization": "Bearer invalid.token.here"})
        log_test("Phase B", "Invalid JWT", "GET /users (Invalid Token)", 401, resp.status_code, resp.status_code == 401, resp.json)

        resp = client.get("/users", headers={"Authorization": f"Bearer {user_a_token}123"})
        log_test("Phase B", "Modified Signature", "GET /users (Modified Sig)", 401, resp.status_code, resp.status_code == 401, resp.json)

        resp = client.get("/users")
        log_test("Phase B", "Missing JWT", "GET /users (No Header)", 401, resp.status_code, resp.status_code == 401, resp.json)

        # C. Permission
        resp = client.get("/users", headers={"Authorization": f"Bearer {admin_token}"})
        log_test("Phase C", "Admin accessing protected route", "GET /users", 200, resp.status_code, resp.status_code == 200, "Success")
        
        resp = client.get("/users", headers={"Authorization": f"Bearer {user_a_token}"})
        log_test("Phase C", "Normal user accessing protected route", "GET /users", 403, resp.status_code, resp.status_code == 403, "Expected 403")

        # D & E. Ownership & Horizontal Esc
        from app.notifications.models import Notification, NotificationType
        notif = Notification(recipient_user_id=str(user_a.id), type=NotificationType.SYSTEM, title="Test", message="Test")
        db.session.add(notif)
        db.session.commit()
        
        resp = client.get(f"/notifications/{notif.id}", headers={"Authorization": f"Bearer {user_a_token}"})
        log_test("Phase D", "Owner reads own resource", f"GET /notifications/{notif.id}", 200, resp.status_code, resp.status_code == 200, "Success")
        
        resp = client.get(f"/notifications/{notif.id}", headers={"Authorization": f"Bearer {user_b_token}"})
        log_test("Phase E", "User reads another's resource (IDOR)", f"GET /notifications/{notif.id}", 403, resp.status_code, resp.status_code == 403, resp.json)

        # F. Vertical Esc
        resp = client.post("/roles", json={"role_code": "HACK", "role_name": "Hack"}, headers={"Authorization": f"Bearer {user_a_token}"})
        log_test("Phase F", "Normal user accessing Admin API", "POST /roles", 403, resp.status_code, resp.status_code == 403, resp.json)
        
        resp = client.put(f"/users/{user_a.id}", json={"status": "active"}, headers={"Authorization": f"Bearer {user_a_token}"})
        log_test("Phase F", "Normal user updating self via Admin API", f"PUT /users/{user_a.id}", 403, resp.status_code, resp.status_code == 403, "Needs users.update")

        resp = client.get("/approval-workflows", headers={"Authorization": f"Bearer {user_a_token}"})
        log_test("Phase D", "Approver reading workflows", "GET /approval-workflows", 200, resp.status_code, resp.status_code == 200, f"Got {resp.status_code}")

        # I. Fuzz Testing
        resp = client.get("/users/invalid-uuid", headers={"Authorization": f"Bearer {admin_token}"})
        log_test("Phase I", "Fuzz invalid UUID format", "GET /users/invalid-uuid", 404, resp.status_code, resp.status_code in [404, 400], "Should be handled")
        
        # H. OWASP
        r_h = client.get(f"/users?limit=1000000", headers={"Authorization": f"Bearer {admin_token}"})
        limit_used = r_h.json.get("meta", {}).get("limit") if r_h.json else None
        results.append({
            "phase": "Phase H",
            "name": "API4 Unrestricted Resource Consumption",
            "request": "GET /users?limit=1000000",
            "expected": 200,
            "actual": r_h.status_code,
            "passed": r_h.status_code == 200,
            "evidence": f"Returned limit: {limit_used}"
        })
        if r_h.status_code == 200 and "meta" in r_h.json and r_h.json["meta"].get("limit", 0) > 1000:
            log_test("Phase H", "API4 Pagination Bypass", "GET /users?limit=1000000", 400, 200, False, f"Limit exceeded max bounds but was accepted: {r_h.json}")

        with open("audit_results.json", "w") as f:
            json.dump(results, f, indent=2)
            
        print(f"Audit completed. Wrote {len(results)} results to audit_results.json")

if __name__ == "__main__":
    run_audit()
