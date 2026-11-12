"""
Seed the disposable OpsForge PostgreSQL database for the Day 4 E2E tests.

SAFETY:
- This script refuses to run unless E2E_ALLOW_DATABASE_RESET=1.
- It accepts only the expected local E2E database identity:
  database=opsforge_e2e_db, user=e2e_user, host=localhost/127.0.0.1,
  port=5441.
- It verifies the connected database identity before running migrations or
  truncating tables.
- Never point this script at a development, staging, or production database.

Run from the repository root (PowerShell):
    $env:E2E_DATABASE_URL = "postgresql://e2e_user:e2e_password@127.0.0.1:5441/opsforge_e2e_db"
    $env:E2E_ALLOW_DATABASE_RESET = "1"
    $env:SECRET_KEY = "local-e2e-secret-change-me"
    $env:JWT_SECRET_KEY = "local-e2e-jwt-secret-change-me"
    $env:VAULT_MASTER_KEY = "<your local E2E vault master key>"
    .\\.venv\\Scripts\\python.exe .\\tests\\e2e\\seed_e2e.py

The secrets above are examples only. Use local test-only values, never production
secrets. VAULT_MASTER_KEY must meet the format/length requirements of your app.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

# Resolve the repository root independently of the current working directory.
def find_repository_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "app").is_dir() and (
            (candidate / "pyproject.toml").exists()
            or (candidate / "alembic.ini").exists()
            or (candidate / ".git").exists()
        ):
            return candidate
    raise RuntimeError(
        "Could not locate the repository root (expected an 'app' directory "
        "and a project marker)."
    )


REPO_ROOT = find_repository_root(Path(__file__).resolve().parent)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


EXPECTED_DATABASE = "opsforge_e2e_db"
EXPECTED_USERNAME = "e2e_user"
EXPECTED_HOSTS = {"localhost", "127.0.0.1"}
EXPECTED_PORT = 5441
RESET_CONFIRMATION = "1"


def require_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is missing. "
            "Set it to a local E2E-only value before running this script."
        )
    return value


def validate_database_url(database_url: str) -> None:
    parsed = urlparse(database_url)

    if parsed.scheme not in {"postgresql", "postgresql+psycopg2", "postgresql+psycopg"}:
        raise RuntimeError(
            f"Refusing database URL scheme {parsed.scheme!r}; PostgreSQL is required."
        )

    host = (parsed.hostname or "").lower()
    port = parsed.port
    database = parsed.path.lstrip("/")
    username = parsed.username

    if host not in EXPECTED_HOSTS:
        raise RuntimeError(
            f"Refusing non-local database host {host!r}; expected localhost or 127.0.0.1."
        )
    if port != EXPECTED_PORT:
        raise RuntimeError(
            f"Refusing database port {port!r}; expected {EXPECTED_PORT}."
        )
    if database != EXPECTED_DATABASE:
        raise RuntimeError(
            f"Refusing database {database!r}; expected {EXPECTED_DATABASE!r}."
        )
    if username != EXPECTED_USERNAME:
        raise RuntimeError(
            f"Refusing database user {username!r}; expected {EXPECTED_USERNAME!r}."
        )


def verify_connected_database(database_url: str) -> None:
    """
    Verify the identity reported by PostgreSQL itself, not just URL text.
    This runs before importing the Flask app, applying migrations, or deleting data.
    """
    import sqlalchemy as sa
    from sqlalchemy.engine import make_url

    engine = sa.create_engine(make_url(database_url), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            identity = connection.execute(
                sa.text(
                    """
                    SELECT
                        current_database() AS database_name,
                        current_user AS database_user,
                        inet_server_port() AS server_port
                    """
                )
            ).mappings().one()

            actual_database = identity["database_name"]
            actual_user = identity["database_user"]
            server_port = identity["server_port"]

            if actual_database != EXPECTED_DATABASE:
                raise RuntimeError(
                    "Connected PostgreSQL database identity mismatch: "
                    f"{actual_database!r}."
                )
            if actual_user != EXPECTED_USERNAME:
                raise RuntimeError(
                    "Connected PostgreSQL user identity mismatch: "
                    f"{actual_user!r}."
                )

            # The published host port is checked in the URL. PostgreSQL inside
            # Docker may report its internal port (usually 5432), so do not
            # incorrectly require inet_server_port() to equal 5441.
            print(
                "Verified PostgreSQL target: "
                f"database={actual_database}, user={actual_user}, "
                f"server_port={server_port}, URL_port={EXPECTED_PORT}"
            )
    finally:
        engine.dispose()


def reset_e2e_database() -> None:
    """
    Truncate public-schema tables except Alembic's version table.
    This is intentionally destructive and is only called after both safety
    checks have passed.
    """
    import sqlalchemy as sa
    from app.platform.extensions import db

    print("Resetting tables in the verified disposable E2E database...")
    try:
        db.session.execute(
            sa.text(
                """
                DO $$
                DECLARE
                    table_record RECORD;
                BEGIN
                    FOR table_record IN
                        SELECT tablename
                        FROM pg_tables
                        WHERE schemaname = 'public'
                          AND tablename <> 'alembic_version'
                    LOOP
                        EXECUTE format(
                            'TRUNCATE TABLE %I.%I RESTART IDENTITY CASCADE',
                            'public',
                            table_record.tablename
                        );
                    END LOOP;
                END
                $$;
                """
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def seed() -> None:
    if os.environ.get("E2E_ALLOW_DATABASE_RESET") != RESET_CONFIRMATION:
        raise RuntimeError(
            "Database reset is disabled. Set E2E_ALLOW_DATABASE_RESET=1 "
            "only when you have confirmed the disposable E2E database is running."
        )

    database_url = require_environment("E2E_DATABASE_URL")
    validate_database_url(database_url)

    # Validate every required input before migrations or destructive reset.
    test_password = require_environment("E2E_TEST_PASSWORD")

    private_key_path = Path(
        os.environ.get(
            "E2E_TARGET_PRIVATE_KEY",
            str(REPO_ROOT / "docker" / "target" / "id_ed25519_opsforge_svc"),
        )
    ).expanduser()

    if not private_key_path.is_file():
        raise FileNotFoundError(
            f"E2E target private key not found: {private_key_path}. "
            "Provide E2E_TARGET_PRIVATE_KEY pointing to the disposable target's "
            "test key. Do not use a personal or production SSH key."
        )

    if not os.access(private_key_path, os.R_OK):
        raise PermissionError(
            f"E2E target private key is not readable: {private_key_path}"
        )

    # Set app configuration only after validating the explicit E2E URL.
    os.environ["APP_ENV"] = "development"
    os.environ["DATABASE_URL"] = database_url
    os.environ["TEST_DATABASE_URL"] = database_url
    os.environ["SECRET_KEY"] = require_environment("SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = require_environment("JWT_SECRET_KEY")
    os.environ["VAULT_MASTER_KEY"] = require_environment("VAULT_MASTER_KEY")

    # Verify the real PostgreSQL endpoint before importing app code or mutating it.
    verify_connected_database(database_url)

    from app import create_app
    from app.platform.extensions import db

    app = create_app(validate_kms=False, testing_bootstrap=False)

    with app.app_context():
        from flask_migrate import upgrade

        print("Applying database migrations...")
        upgrade()

        # Recheck the identity using the actual Flask application's connection.
        import sqlalchemy as sa

        app_identity = db.session.execute(
            sa.text("SELECT current_database() AS db, current_user AS db_user")
        ).mappings().one()
        if (
            app_identity["db"] != EXPECTED_DATABASE
            or app_identity["db_user"] != EXPECTED_USERNAME
        ):
            raise RuntimeError(
                "Flask application is connected to an unexpected database. "
                "Aborting before reset."
            )

        reset_e2e_database()

        from app.vault.bootstrap import seed_kms
        from app.identity.models import User, UserStatus
        from app.permissions.models import Permission, PermissionAction
        from app.policy_engine.models import AccessPolicy, PolicyEffect
        from app.resources.models import (
            ConnectionMethod,
            Resource,
            ResourceType,
        )
        from app.role_permissions.models import RolePermission
        from app.roles.models import Role, UserRole
        from app.vault.crypto import EncryptionService
        from app.vault.domain import SecretFactory, SecretVersion
        from app.vault.kms_factory import KMSProviderFactory
        from app.vault.repository import SqlAlchemyVaultRepository
        from werkzeug.security import generate_password_hash

        print("Bootstrapping test KMS...")
        seed_kms()


        password_hash = generate_password_hash(test_password)

        print("Creating test identities...")
        admin_user = User(
            id=uuid.uuid4(),
            employee_id="E001",
            full_name="Admin User",
            username="admin_user",
            email="admin@example.com",
            password_hash=password_hash,
            status=UserStatus.ACTIVE,
        )
        requester_vault_read = User(
            id=uuid.uuid4(),
            employee_id="E002",
            full_name="Vault Requester",
            username="requester_vault_read",
            email="vault@example.com",
            password_hash=password_hash,
            status=UserStatus.ACTIVE,
        )
        requester_no_vault = User(
            id=uuid.uuid4(),
            employee_id="E003",
            full_name="No Vault Requester",
            username="requester_no_vault",
            email="novault@example.com",
            password_hash=password_hash,
            status=UserStatus.ACTIVE,
        )
        approver_user = User(
            id=uuid.uuid4(),
            employee_id="E004",
            full_name="Approver User",
            username="approver_user",
            email="approver@example.com",
            password_hash=password_hash,
            status=UserStatus.ACTIVE,
        )
        db.session.add_all(
            [admin_user, requester_vault_read, requester_no_vault, approver_user]
        )
        db.session.flush()

        print("Creating roles and permissions...")
        role_vault_read = Role(
            id=uuid.uuid4(),
            role_name="Vault Reader",
            role_code="VAULT_READER",
            description="Can read vault",
        )
        role_no_vault = Role(
            id=uuid.uuid4(),
            role_name="No Vault",
            role_code="NO_VAULT",
            description="No vault access",
        )
        role_approver = Role(
            id=uuid.uuid4(),
            role_name="Approver",
            role_code="APPROVER",
            description="Approver role",
        )
        role_admin = Role(
            id=uuid.uuid4(),
            role_name="Admin",
            role_code="ADMIN",
            description="Admin role",
        )

        perm_vault_read = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_VAULT_READ",
            permission_name="Vault Read",
            action=PermissionAction.READ,
        )
        perm_vault_write = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_VAULT_UPDATE",
            permission_name="Vault Write",
            action=PermissionAction.UPDATE,
        )
        perm_ar_approve = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_ACCESS_REQUESTS_APPROVE",
            permission_name="AR Approve",
            action=PermissionAction.APPROVE,
        )
        perm_ar_create = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_ACCESS_REQUESTS_CREATE",
            permission_name="AR Create",
            action=PermissionAction.CREATE,
        )
        perm_users_read = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_USERS_READ",
            permission_name="Users Read",
            action=PermissionAction.READ,
        )
        perm_jit_grants_update = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_JIT_GRANTS_UPDATE",
            permission_name="JIT Grants Update",
            action=PermissionAction.UPDATE,
        )
        perm_jit_grants_create = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_JIT_GRANTS_CREATE",
            permission_name="JIT Grants Create",
            action=PermissionAction.CREATE,
        )
        perm_jit_grants_read = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_JIT_GRANTS_READ",
            permission_name="JIT Grants Read",
            action=PermissionAction.READ,
        )
        perm_roles_read = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_ROLES_READ",
            permission_name="Roles Read",
            action=PermissionAction.READ,
        )
        perm_perms_read = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_PERMISSIONS_READ",
            permission_name="Permissions Read",
            action=PermissionAction.READ,
        )
        perm_res_read = Permission(
            id=uuid.uuid4(),
            permission_code="PERM_RESOURCES_READ",
            permission_name="Resources Read",
            action=PermissionAction.READ,
        )

        db.session.add_all(
            [
                role_vault_read,
                role_no_vault,
                role_approver,
                role_admin,
                perm_vault_read,
                perm_vault_write,
                perm_ar_approve,
                perm_ar_create,
                perm_users_read,
                perm_jit_grants_update,
                perm_jit_grants_create,
                perm_jit_grants_read,
                perm_roles_read,
                perm_perms_read,
                perm_res_read,
            ]
        )
        db.session.flush()

        common_permissions = [
            perm_users_read,
            perm_roles_read,
            perm_perms_read,
            perm_res_read,
            perm_ar_create,
        ]
        for role in (role_vault_read, role_no_vault, role_approver):
            for permission in common_permissions:
                db.session.add(
                    RolePermission(role_id=role.id, permission_id=permission.id)
                )

        for permission in (perm_vault_read,):
            db.session.add(
                RolePermission(role_id=role_vault_read.id, permission_id=permission.id)
            )
        for permission in (perm_ar_approve, perm_vault_read):
            db.session.add(
                RolePermission(role_id=role_approver.id, permission_id=permission.id)
            )
        for permission in (
            perm_jit_grants_read,
            perm_jit_grants_create,
            perm_jit_grants_update,
            perm_vault_read,
        ):
            db.session.add(
                RolePermission(role_id=role_admin.id, permission_id=permission.id)
            )

        db.session.add_all(
            [
                UserRole(user_id=requester_vault_read.id, role_id=role_vault_read.id),
                UserRole(user_id=requester_no_vault.id, role_id=role_no_vault.id),
                UserRole(user_id=approver_user.id, role_id=role_approver.id),
                UserRole(user_id=admin_user.id, role_id=role_admin.id),
                UserRole(user_id=admin_user.id, role_id=role_approver.id),
            ]
        )
        db.session.flush()

        target_host = os.environ.get("TARGET_SSH_HOST", "127.0.0.1")
        target_port = int(os.environ.get("TARGET_SSH_PORT", "2222"))
        target_fingerprint = os.environ.get(
            "TARGET_SSH_HOST_KEY_FINGERPRINT",
            "SHA256:ZosTjYvolo0fF43SEkosFh0lZqAFV/Uh/sMsR3O7oSs",
        )
        target_pinned_host_key = os.environ.get(
            "TARGET_SSH_PINNED_HOST_KEY",
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHrnP/LjJYs6IyvEvO/IOnf2iK7mobCHGKeIx5kWURgO",
        )

        print("Creating disposable SSH resource...")
        resource = Resource(
            id=uuid.uuid4(),
            resource_name="E2E Disposable Target",
            resource_code="E2E_DISPOSABLE_TARGET",
            resource_type=ResourceType.SERVER,
            hostname_ip=target_host,
            port=target_port,
            connection_method=ConnectionMethod.SSH,
            host_key_fingerprint=target_fingerprint,
            host_key_trusted_at=datetime.now(timezone.utc),
            pinned_host_key=target_pinned_host_key,
        )
        db.session.add(resource)
        db.session.flush()

        print("Creating encrypted SSH credential...")
        secret = SecretFactory.create_new_secret(resource.id)
        kms = KMSProviderFactory.resolve_active_provider(db.session)
        crypto = EncryptionService(kms)

        encrypted_dek, encrypted_payload, metadata = crypto.encrypt_payload(
            resource.id, secret.id, private_key_path.read_bytes()
        )
        secret_version = SecretVersion(
            id=uuid.uuid4(),
            secret_id=secret.id,
            encrypted_dek=encrypted_dek,
            encrypted_payload=encrypted_payload,
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
            created_by=admin_user.id,
        )
        secret.add_version(secret_version)
        vault_repository = SqlAlchemyVaultRepository(db.session)
        vault_repository.save(secret)
        db.session.flush()

        print("Creating access policies...")
        access_policy = AccessPolicy(
            id=uuid.uuid4(),
            name="E2E Allow Policy",
            conditions={},
            requires_approval=False,
            effect=PolicyEffect.ALLOW,
            priority=100,
            enabled=True,
        )
        db.session.add(access_policy)

        # Retained from the original E2E fixture because the current application
        # path appears to consult ResourceAccessPolicy. This does NOT prove that
        # the AccessPolicy engine is correct; test that behavior separately.
        from app.resources.models import ResourceAccessPolicy

        resource_access_policy = ResourceAccessPolicy(
            id=uuid.uuid4(),
            resource_id=resource.id,
            role_id=role_vault_read.id,
            approval_required=False,
        )
        db.session.add(resource_access_policy)
        db.session.flush()

        print("Seeding Phase 12 Day 4 access workflow...")
        from app.access_requests.models import AccessRequest, AccessRequestStatus
        from app.jit_access.models import JITAccessGrant, JITGrantStatus
        from app.target_accounts.models import (
            TargetAccountBinding,
            TargetAccountBindingStatus,
        )

        target_binding = TargetAccountBinding(
            id=uuid.uuid4(),
            control_plane_user_id=admin_user.id,
            resource_id=resource.id,
            target_os_username="opsforge-svc",
            ssh_credential_id=secret.id,
            status=TargetAccountBindingStatus.ACTIVE,
        )
        db.session.add(target_binding)
        db.session.flush()

        access_request = AccessRequest(
            id=uuid.uuid4(),
            request_number="AR-DAY4-001",
            requester_id=admin_user.id,
            requested_resource_id=resource.id,
            requested_role_id=role_approver.id,
            business_justification="Day 4 E2E Session",
            status=AccessRequestStatus.APPROVED,
            requested_end=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.session.add(access_request)
        db.session.flush()

        jit_grant = JITAccessGrant(
            id=uuid.uuid4(),
            user_id=admin_user.id,
            role_id=role_approver.id,
            resource_id=resource.id,
            target_account_binding_id=target_binding.id,
            command_set_id="system_health_check",
            approval_request_id=access_request.id,
            status=JITGrantStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.session.add(jit_grant)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        print("E2E database seeded successfully.")
        print("Test users:")
        print("  admin_user")
        print("  requester_vault_read")
        print("  requester_no_vault")
        print("  approver_user")
        print("Use E2E_TEST_PASSWORD for their local test login password.")


if __name__ == "__main__":
    try:
        seed()
    except Exception as exc:
        print(f"ERROR: E2E seeding aborted: {exc}", file=sys.stderr)
        raise
