"""Phase D: Migration Safety Tests for Day 4 migration 4f5394bb6534.

Tests upgrade, downgrade, and re-upgrade of the migration that adds
FAILED, SECURITY_UNCERTAIN, REVOCATION_PENDING, and REVOCATION_RUNNING
statuses to jit_access_grants.

This test script runs against an isolated, disposable database
(opsforge_migration_test) — never against opsforge_db or opsforge_e2e_db.

Uses raw Alembic with a standalone env.py to avoid Flask-Migrate dependency.
"""
import os
import re
import sys
import traceback

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

# ---------------------------------------------------------------------------
# Configuration: disposable test database only
# ---------------------------------------------------------------------------
TEST_DB_URL = os.environ.get(
    "MIGRATION_TEST_DB_URL",
    "postgresql://opsforge:opsforge@localhost:5432/opsforge_migration_test",
)

# The revision IDs involved
DAY4_REVISION = "4f5394bb6534"
PRE_DAY4_REVISION = "3f4294aa5423"

# Safety: refuse to run against the real databases
assert "opsforge_e2e_db" not in TEST_DB_URL, "REFUSING to run against E2E database"
assert "opsforge_migration_test" in TEST_DB_URL, (
    f"REFUSING to run against non-test database: {TEST_DB_URL}"
)


def get_alembic_config():
    """Create an Alembic Config that bypasses Flask-Migrate."""
    cfg = Config()
    cfg.set_main_option("script_location", "/app/migrations")
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    # Point to the ini file for logging config
    cfg.config_file_name = "/app/migrations/alembic.ini"
    return cfg


# We need a standalone env.py that doesn't depend on Flask's current_app.
# Write it to a temp file and override the script_location's env.py.
STANDALONE_ENV_PY = '''
import logging
from logging.config import fileConfig

from alembic import context
import sqlalchemy as sa

config = context.config

try:
    fileConfig(config.config_file_name)
except Exception:
    pass

logger = logging.getLogger("alembic.env")


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=sa.MetaData(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = sa.engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=sa.pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=sa.MetaData())
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''


def get_engine():
    return sa.create_engine(TEST_DB_URL)


def setup_standalone_env():
    """Backup original env.py and write a standalone version."""
    env_path = "/app/migrations/env.py"
    backup_path = "/app/migrations/env.py.bak"

    # Backup original
    if not os.path.exists(backup_path):
        with open(env_path, "r") as f:
            original = f.read()
        with open(backup_path, "w") as f:
            f.write(original)

    # Write standalone
    with open(env_path, "w") as f:
        f.write(STANDALONE_ENV_PY)


def restore_original_env():
    """Restore the original Flask-Migrate env.py."""
    env_path = "/app/migrations/env.py"
    backup_path = "/app/migrations/env.py.bak"

    if os.path.exists(backup_path):
        with open(backup_path, "r") as f:
            original = f.read()
        with open(env_path, "w") as f:
            f.write(original)
        os.remove(backup_path)


def get_constraint_values(engine):
    """Return the set of allowed status values from the CHECK constraint."""
    with engine.connect() as conn:
        result = conn.execute(sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'jit_access_grants'::regclass AND contype = 'c'"
        ))
        for row in result:
            defn = row[0]
            if "status" in defn.lower():
                values = set(re.findall(r"'(\w+)'", defn))
                # Filter out SQL type keywords from ARRAY format
                values -= {"character", "varying", "text"}
                return values
        return set()



def get_column_length(engine, table, column):
    """Return the character_maximum_length for a VARCHAR column."""
    with engine.connect() as conn:
        result = conn.execute(sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ), {"table": table, "column": column})
        row = result.fetchone()
        return row[0] if row else None


def get_alembic_version(engine):
    """Get current alembic version from the test database."""
    with engine.connect() as conn:
        try:
            result = conn.execute(sa.text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            return row[0] if row else None
        except Exception:
            return None


def insert_grant_with_status(engine, status_value):
    """Insert a minimal jit_access_grants row with the given status."""
    from uuid import uuid4

    with engine.connect() as conn:
        # Check for existing seed data
        user_row = conn.execute(sa.text("SELECT id FROM users LIMIT 1")).fetchone()

        if not user_row:
            uid = uuid4()
            rid = uuid4()
            resid = uuid4()
            reqid = uuid4()

            conn.execute(sa.text(
                "INSERT INTO users (id, employee_id, username, email, full_name, status, password_hash, created_at, updated_at) "
                "VALUES (:id, 'EMP001', 'migtest', 'migtest@test.com', 'Migration Tester', 'active', 'nohash', NOW(), NOW())"
            ), {"id": str(uid)})
            conn.execute(sa.text(
                "INSERT INTO roles (id, role_code, role_name, role_type, status, created_at, updated_at) "
                "VALUES (:id, 'ROLE_TEST', 'Test Role', 'custom', 'active', NOW(), NOW())"
            ), {"id": str(rid)})
            conn.execute(sa.text(
                "INSERT INTO resources (id, resource_code, resource_name, resource_type, environment, criticality, status, created_at, updated_at) "
                "VALUES (:id, 'RES_TEST', 'Test Resource', 'server', 'prod', 'medium', 'active', NOW(), NOW())"
            ), {"id": str(resid)})
            conn.execute(sa.text(
                "INSERT INTO access_requests (id, request_number, requester_id, requested_resource_id, requested_role_id, business_justification, status, priority, created_at, updated_at) "
                "VALUES (:id, 'REQ-001', :uid, :resid, :rid, 'test justification', 'pending', 'medium', NOW(), NOW())"
            ), {"id": str(reqid), "uid": str(uid), "resid": str(resid), "rid": str(rid)})
            conn.commit()
            user_id = str(uid)
            role_id = str(rid)
            resource_id = str(resid)
            request_id = str(reqid)
        else:
            user_id = str(user_row[0])
            role_id = str(conn.execute(sa.text("SELECT id FROM roles LIMIT 1")).fetchone()[0])
            resource_id = str(conn.execute(sa.text("SELECT id FROM resources LIMIT 1")).fetchone()[0])
            request_id = str(conn.execute(sa.text("SELECT id FROM access_requests LIMIT 1")).fetchone()[0])

        grant_id = uuid4()
        conn.execute(sa.text(
            "INSERT INTO jit_access_grants (id, user_id, role_id, resource_id, approval_request_id, "
            "status, revocation_attempts, created_at, updated_at) "
            "VALUES (:id, :uid, :rid, :resid, :reqid, :status, 0, NOW(), NOW())"
        ), {
            "id": str(grant_id),
            "uid": user_id,
            "rid": role_id,
            "resid": resource_id,
            "reqid": request_id,
            "status": status_value,
        })
        conn.commit()
        return grant_id


def count_grants(engine):
    with engine.connect() as conn:
        return conn.execute(sa.text("SELECT COUNT(*) FROM jit_access_grants")).scalar()


def cleanup_grants(engine):
    with engine.connect() as conn:
        conn.execute(sa.text("DELETE FROM jit_access_grants"))
        conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

ORIGINAL_STATUSES = {"pending", "active", "expired", "revoked", "denied"}
DAY4_STATUSES = {"pending", "active", "revocation_pending", "revocation_running",
                 "expired", "revoked", "denied", "failed", "security_uncertain"}


def test_upgrade_to_day4():
    """Test 1: Upgrade from pre-Day4 to Day4 revision."""
    print("\n=== Test 1: Upgrade to Day 4 ===")
    cfg = get_alembic_config()
    engine = get_engine()

    # Migrate to pre-Day4
    print(f"  Migrating to pre-Day4 revision {PRE_DAY4_REVISION}...")
    command.upgrade(cfg, PRE_DAY4_REVISION)

    pre_values = get_constraint_values(engine)
    pre_length = get_column_length(engine, "jit_access_grants", "status")
    print(f"  Pre-upgrade constraint values: {sorted(pre_values)}")
    print(f"  Pre-upgrade column length: {pre_length}")
    assert pre_values == ORIGINAL_STATUSES, f"Pre-upgrade constraint mismatch: {pre_values}"

    # Upgrade to Day4
    print(f"  Upgrading to Day4 revision {DAY4_REVISION}...")
    command.upgrade(cfg, DAY4_REVISION)

    post_values = get_constraint_values(engine)
    post_length = get_column_length(engine, "jit_access_grants", "status")
    print(f"  Post-upgrade constraint values: {sorted(post_values)}")
    print(f"  Post-upgrade column length: {post_length}")
    assert post_values == DAY4_STATUSES, f"Post-upgrade constraint mismatch: {post_values}"
    assert post_length == 32, f"Column length should be 32, got {post_length}"

    # Insert rows with new statuses
    for status in ("failed", "security_uncertain", "revocation_pending", "revocation_running"):
        insert_grant_with_status(engine, status)
        print(f"  ✓ Inserted grant with status '{status}'")

    cleanup_grants(engine)
    print("  PASSED")


def test_downgrade_empty_table():
    """Test 2: Downgrade with no rows using new statuses."""
    print("\n=== Test 2: Downgrade with empty table ===")
    cfg = get_alembic_config()
    engine = get_engine()

    command.upgrade(cfg, DAY4_REVISION)
    cleanup_grants(engine)

    print(f"  Downgrading to {PRE_DAY4_REVISION}...")
    command.downgrade(cfg, PRE_DAY4_REVISION)

    post_values = get_constraint_values(engine)
    post_length = get_column_length(engine, "jit_access_grants", "status")
    print(f"  Post-downgrade constraint values: {sorted(post_values)}")
    print(f"  Post-downgrade column length: {post_length}")
    assert post_values == ORIGINAL_STATUSES, f"Post-downgrade constraint mismatch: {post_values}"
    assert post_length == 7, f"Post-downgrade column length should be 7, got {post_length}"
    print("  PASSED")


def test_downgrade_with_old_status_rows():
    """Test 3: Downgrade with rows using only old statuses succeeds."""
    print("\n=== Test 3: Downgrade with old-status rows ===")
    cfg = get_alembic_config()
    engine = get_engine()

    command.upgrade(cfg, DAY4_REVISION)
    cleanup_grants(engine)

    for status in ("pending", "active", "expired", "revoked", "denied"):
        insert_grant_with_status(engine, status)
    initial_count = count_grants(engine)
    print(f"  Inserted {initial_count} grants with old statuses")

    print(f"  Downgrading to {PRE_DAY4_REVISION}...")
    command.downgrade(cfg, PRE_DAY4_REVISION)

    final_count = count_grants(engine)
    print(f"  Post-downgrade row count: {final_count}")
    assert final_count == initial_count, f"Row count changed: {initial_count} → {final_count}"

    cleanup_grants(engine)
    print("  PASSED")


def test_downgrade_with_new_status_rows_blocked():
    """Test 4: Downgrade with rows using new statuses is blocked."""
    print("\n=== Test 4: Downgrade blocked when new-status rows exist ===")
    cfg = get_alembic_config()
    engine = get_engine()

    command.upgrade(cfg, DAY4_REVISION)
    cleanup_grants(engine)

    insert_grant_with_status(engine, "security_uncertain")
    insert_grant_with_status(engine, "failed")
    print("  Inserted grants with 'security_uncertain' and 'failed'")

    try:
        command.downgrade(cfg, PRE_DAY4_REVISION)
        cleanup_grants(engine)
        raise AssertionError("Downgrade should have raised RuntimeError but succeeded!")
    except RuntimeError as e:
        print(f"  Downgrade correctly blocked: {e}")
        # Verify still at Day4 revision
        ver = get_alembic_version(engine)
        print(f"  Current revision after blocked downgrade: {ver}")
        assert ver == DAY4_REVISION, f"Expected {DAY4_REVISION}, got {ver}"
        cleanup_grants(engine)
        print("  PASSED")


def test_re_upgrade():
    """Test 5: Re-upgrade after downgrade produces correct state."""
    print("\n=== Test 5: Re-upgrade after downgrade ===")
    cfg = get_alembic_config()
    engine = get_engine()

    command.upgrade(cfg, DAY4_REVISION)
    cleanup_grants(engine)
    command.downgrade(cfg, PRE_DAY4_REVISION)

    print(f"  Re-upgrading to {DAY4_REVISION}...")
    command.upgrade(cfg, DAY4_REVISION)

    post_values = get_constraint_values(engine)
    post_length = get_column_length(engine, "jit_access_grants", "status")
    print(f"  Post-re-upgrade constraint values: {sorted(post_values)}")
    print(f"  Post-re-upgrade column length: {post_length}")
    assert post_values == DAY4_STATUSES, f"Re-upgrade constraint mismatch: {post_values}"
    assert post_length == 32, f"Re-upgrade column length should be 32, got {post_length}"

    for status in ("failed", "security_uncertain", "revocation_pending", "revocation_running"):
        insert_grant_with_status(engine, status)
        print(f"  ✓ Inserted grant with status '{status}' after re-upgrade")

    cleanup_grants(engine)
    print("  PASSED")


def test_downgrade_with_revocation_status_rows_blocked():
    """Test 6: Downgrade also blocked for revocation_pending/revocation_running."""
    print("\n=== Test 6: Downgrade blocked for revocation status rows ===")
    cfg = get_alembic_config()
    engine = get_engine()

    command.upgrade(cfg, DAY4_REVISION)
    cleanup_grants(engine)

    insert_grant_with_status(engine, "revocation_pending")
    insert_grant_with_status(engine, "revocation_running")
    print("  Inserted grants with 'revocation_pending' and 'revocation_running'")

    try:
        command.downgrade(cfg, PRE_DAY4_REVISION)
        cleanup_grants(engine)
        raise AssertionError("Downgrade should have raised RuntimeError but succeeded!")
    except RuntimeError as e:
        print(f"  Downgrade correctly blocked: {e}")
        cleanup_grants(engine)
        print("  PASSED")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("Phase D: Migration Safety Tests for Day 4 (4f5394bb6534)")
    print(f"Test database: {TEST_DB_URL}")
    print("=" * 70)

    # Setup standalone env.py (bypass Flask-Migrate)
    setup_standalone_env()

    results = {}
    tests = [
        test_upgrade_to_day4,
        test_downgrade_empty_table,
        test_downgrade_with_old_status_rows,
        test_downgrade_with_new_status_rows_blocked,
        test_re_upgrade,
        test_downgrade_with_revocation_status_rows_blocked,
    ]

    try:
        for test_fn in tests:
            try:
                test_fn()
                results[test_fn.__name__] = "PASSED"
            except Exception as e:
                results[test_fn.__name__] = f"FAILED: {e}"
                traceback.print_exc()
    finally:
        # Always restore original env.py
        restore_original_env()
        print("\n  [Restored original Flask-Migrate env.py]")

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    all_passed = True
    for name, result in results.items():
        status = "✓" if result == "PASSED" else "✗"
        print(f"  {status} {name}: {result}")
        if result != "PASSED":
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
