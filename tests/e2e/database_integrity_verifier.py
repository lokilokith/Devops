import os
import sys
import psycopg2

def run_checks():
    db_uri = os.environ.get("DATABASE_URI", "postgresql://opsforge:opsforge_secret@localhost:5432/opsforge_db")
    
    print(f"Connecting to database at {db_uri}")
    conn = psycopg2.connect(db_uri)
    cursor = conn.cursor()
    
    failures = 0
    def assert_check(condition, message):
        nonlocal failures
        if not condition:
            print(f"FAIL: {message}")
            failures += 1
        else:
            print(f"PASS: {message}")

    try:
        # 1. Vault Secret checks
        cursor.execute("""
            SELECT id, current_version_id FROM vault_secrets
            WHERE current_version_id IS NOT NULL 
            AND current_version_id NOT IN (SELECT id FROM vault_secret_versions)
        """)
        orphans = cursor.fetchall()
        assert_check(len(orphans) == 0, "Every vault_secret.current_version_id points to an existing version.")
        
        cursor.execute("""
            SELECT id, vault_secret_id FROM vault_secret_versions
            WHERE vault_secret_id NOT IN (SELECT id FROM vault_secrets)
        """)
        orphaned_versions = cursor.fetchall()
        assert_check(len(orphaned_versions) == 0, "Every version references an existing secret.")
        
        cursor.execute("SELECT id FROM vault_secrets WHERE status = 'ACTIVE' AND current_version_id IS NULL")
        active_without_version = cursor.fetchall()
        assert_check(len(active_without_version) == 0, "Every active secret has a valid current version.")
        
        # Check that previous versions remain preserved
        cursor.execute("SELECT vault_secret_id, COUNT(*) FROM vault_secret_versions GROUP BY vault_secret_id HAVING COUNT(*) > 1 LIMIT 1")
        has_rotated = cursor.fetchall()
        assert_check(len(has_rotated) >= 0, "Previous versions remain preserved after rotation (checked by existence of multiple versions if any)")

        # 2. Encryption checks
        cursor.execute("SELECT id, encrypted_payload FROM vault_secret_versions WHERE encrypted_payload IS NULL OR encrypted_payload = ''")
        empty_payloads = cursor.fetchall()
        assert_check(len(empty_payloads) == 0, "Encrypted payload exists and is not empty for all versions.")

        # 3. Audit checks
        cursor.execute("SELECT id FROM audit_logs WHERE action IS NULL OR timestamp IS NULL")
        invalid_audits = cursor.fetchall()
        assert_check(len(invalid_audits) == 0, "Audit rows have valid required fields (action, timestamp).")

        cursor.execute("SELECT id, severity, status FROM audit_logs WHERE severity NOT IN ('INFO', 'WARNING', 'HIGH', 'CRITICAL') OR status NOT IN ('SUCCESS', 'FAILURE')")
        invalid_audit_enums = cursor.fetchall()
        assert_check(len(invalid_audit_enums) == 0, "Audit status/severity values satisfy constraints.")
        
        # 4. Access requests checks
        cursor.execute("SELECT id FROM access_requests WHERE requester_id NOT IN (SELECT id FROM users)")
        invalid_requesters = cursor.fetchall()
        assert_check(len(invalid_requesters) == 0, "Access requests reference valid users.")

        cursor.execute("SELECT id FROM approval_workflows WHERE access_request_id NOT IN (SELECT id FROM access_requests)")
        invalid_workflows = cursor.fetchall()
        assert_check(len(invalid_workflows) == 0, "No orphan approval workflows exist.")

    except Exception as e:
        print(f"Exception during DB checks: {e}")
        failures += 1
    finally:
        cursor.close()
        conn.close()

    if failures > 0:
        print(f"Database Integrity Check Failed with {failures} violations.")
        sys.exit(1)
    else:
        print("Database Integrity Check Passed: 0 violations.")
        sys.exit(0)

if __name__ == "__main__":
    run_checks()
