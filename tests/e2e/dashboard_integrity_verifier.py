import requests
import sys

BASE_URL = "http://localhost/api/v1"
ADMIN_CREDS = {"username": "admin", "password": "secret123"}
evidence_lines = []

def report(metric, expected, actual, passed):
    result = "PASS" if passed else "FAIL"
    evidence_lines.append(f"| {metric} | {expected} | {actual} | **{result}** |")
    if not passed:
        print(f"FAIL: {metric}. Expected: {expected}, Actual: {actual}")

def run_checks():
    r = requests.post(f"{BASE_URL}/auth/login", json=ADMIN_CREDS)
    if r.status_code != 200:
        print("FAIL: Could not login as admin.")
        sys.exit(1)
    admin_token = r.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    evidence_lines.append("# Dashboard Integrity Evidence\n")
    evidence_lines.append("| Metric | Expected | Actual | Result |")
    evidence_lines.append("|---|---|---|---|")

    r = requests.get(f"{BASE_URL}/metrics/dashboard", headers=headers)
    
    passed = r.status_code == 200
    report("Dashboard API Availability", "HTTP 200", f"HTTP {r.status_code}", passed)
    if not passed:
        print("FAIL: Dashboard API not reachable.")
        with open("docs/evidence/dashboard_integrity_evidence.md", "w") as f:
            f.write("\n".join(evidence_lines) + "\n")
        sys.exit(1)

    data = r.json().get("data", {})
    
    # Check access_requests
    ar = data.get("access_requests", {})
    passed = "pending" in ar and "approved" in ar
    report("Access Requests Aggregation", "pending/approved keys exist", f"Keys: {list(ar.keys())}", passed)
    
    # Check active_secrets
    active_secrets = data.get("active_secrets")
    passed = isinstance(active_secrets, int)
    report("Active Secrets Aggregation", "Integer active_secrets exists", f"{type(active_secrets).__name__}", passed)
    
    # Check unread_notifications
    unread = data.get("unread_notifications")
    passed = isinstance(unread, int)
    report("Unread Notifications Aggregation", "Integer unread_notifications exists", f"{type(unread).__name__}", passed)

    with open("docs/evidence/dashboard_integrity_evidence.md", "w") as f:
        f.write("\n".join(evidence_lines) + "\n")

    failures = sum(1 for line in evidence_lines if "**FAIL**" in line)
    if failures > 0:
        print(f"Dashboard Integrity Check Failed with {failures} violations.")
        sys.exit(1)
    else:
        print("Dashboard Integrity Check Passed: 0 violations.")
        sys.exit(0)

if __name__ == "__main__":
    run_checks()
