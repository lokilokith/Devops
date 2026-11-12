import pytest
import requests
import sqlalchemy as sa
from sqlalchemy import text


def test_database_invariants(e2e_base_url: str):
    engine = sa.create_engine(
        "postgresql://e2e_user:e2e_password@localhost:5441/opsforge_e2e_db"
    )
    _api_url = e2e_base_url  # noqa: F841 – fixture parameter, kept for reference

    with engine.connect() as conn:
        # 1. No duplicate ACTIVE leases for the same secret
        dupes = conn.execute(text("""
            SELECT vault_secret_id, COUNT(*)
            FROM credential_leases
            WHERE status = 'ACTIVE'
            GROUP BY vault_secret_id
            HAVING COUNT(*) > 1
        """)).fetchall()
        assert len(dupes) == 0, f"Found duplicate active leases: {dupes}"

        # 2. No CHECKED_OUT secret without ACTIVE lease
        checked_out_secrets = conn.execute(text("""
            SELECT id FROM vault_secrets
            WHERE status = 'CHECKED_OUT'
            AND NOT EXISTS (
                SELECT 1 FROM credential_leases
                WHERE vault_secret_id = vault_secrets.id AND status = 'ACTIVE'
            )
        """)).fetchall()
        assert (
            len(checked_out_secrets) == 0
        ), f"Found CHECKED_OUT secrets without ACTIVE leases: {checked_out_secrets}"

        # 3. Alembic state
        alembic_version = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        assert alembic_version is not None, "Alembic version not found in E2E DB"

    # 7 & 8. Plaintext absent from audit logs
    # Admin login to check audit
    resp = requests.post(
        f"{e2e_base_url}/api/v1/auth/login",
        json={"username": "admin_user", "password": "testpassword"},
    )
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]

    audit_resp = requests.get(
        f"{e2e_base_url}/api/v1/audit/", headers={"Authorization": f"Bearer {token}"}
    )
    assert audit_resp.status_code == 200
    logs = str(audit_resp.json())

    has_leak = "e2e_synthetic_secret_value_123!" in logs
    if has_leak:
        pytest.fail("Synthetic plaintext credential found in audit logs!")
