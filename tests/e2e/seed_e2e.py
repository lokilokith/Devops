import os
import sys

# Ensure the root of the project is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Configure for E2E seeding BEFORE importing anything else
os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = (
    "postgresql://e2e_user:e2e_password@localhost:5441/opsforge_e2e_db"
)
os.environ["TEST_DATABASE_URL"] = (
    "postgresql://e2e_user:e2e_password@localhost:5441/opsforge_e2e_db"
)
os.environ["SECRET_KEY"] = "e2e_secret_key"
os.environ["JWT_SECRET_KEY"] = "e2e_jwt_secret_key"
os.environ["VAULT_MASTER_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="

from app import create_app  # noqa: E402
from app.platform.extensions import db  # noqa: E402


def seed():
    app = create_app(validate_kms=False, testing_bootstrap=False)

    with app.app_context():
        print("Ensuring migrations are up to date...")
        from flask_migrate import upgrade

        upgrade()

        print("Truncating all tables...")
        import sqlalchemy as sa

        db.session.execute(sa.text("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version') LOOP
                    EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """))
        db.session.commit()

        from app.vault.bootstrap import seed_kms

        seed_kms()
        import uuid

        from app.identity.models import User, UserStatus
        from app.permissions.models import Permission, PermissionAction
        from app.policy_engine.models import AccessPolicy, PolicyEffect
        from app.resources.models import Resource
        from app.role_permissions.models import RolePermission
        from app.roles.models import Role, UserRole
        from app.vault.crypto import EncryptionService
        from app.vault.kms_factory import KMSProviderFactory
        from app.vault.repository import SqlAlchemyVaultRepository

        print("Creating identities...")

        # We need specific plaintext passwords for playwright logins
        from werkzeug.security import generate_password_hash

        password_hash = generate_password_hash("testpassword")

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
        db.session.commit()

        # Setup roles and permissions
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
                perm_vault_read,
                perm_vault_write,
                perm_ar_approve,
                perm_ar_create,
                perm_users_read,
                perm_roles_read,
                perm_perms_read,
                perm_res_read,
            ]
        )
        db.session.commit()

        for role in [role_vault_read, role_no_vault, role_approver]:
            db.session.add(
                RolePermission(role_id=role.id, permission_id=perm_users_read.id)
            )
            db.session.add(
                RolePermission(role_id=role.id, permission_id=perm_roles_read.id)
            )
            db.session.add(
                RolePermission(role_id=role.id, permission_id=perm_perms_read.id)
            )
            db.session.add(
                RolePermission(role_id=role.id, permission_id=perm_res_read.id)
            )
            db.session.add(
                RolePermission(role_id=role.id, permission_id=perm_ar_create.id)
            )

        db.session.add(
            RolePermission(role_id=role_vault_read.id, permission_id=perm_vault_read.id)
        )
        db.session.add(
            RolePermission(role_id=role_approver.id, permission_id=perm_ar_approve.id)
        )
        db.session.add(
            RolePermission(role_id=role_approver.id, permission_id=perm_vault_read.id)
        )

        db.session.add(
            UserRole(user_id=requester_vault_read.id, role_id=role_vault_read.id)
        )
        db.session.add(
            UserRole(user_id=requester_no_vault.id, role_id=role_no_vault.id)
        )
        db.session.add(UserRole(user_id=approver_user.id, role_id=role_approver.id))
        db.session.add(UserRole(user_id=admin_user.id, role_id=role_approver.id))

        db.session.commit()

        # Setup test resource
        from app.resources.models import ResourceType

        test_resource = Resource(
            id=uuid.uuid4(),
            resource_name="E2E Database Password",
            resource_code="DB_PROD_PASS",
            resource_type=ResourceType.DATABASE,
        )
        db.session.add(test_resource)
        db.session.commit()

        # Setup vault secret for the resource
        from app.vault.domain import SecretFactory

        secret = SecretFactory.create_new_secret(test_resource.id)

        # Encrypt deterministic plaintext credential
        kms = KMSProviderFactory.resolve_active_provider(db.session)
        crypto = EncryptionService(kms)
        synthetic_credential = b"e2e_synthetic_secret_value_123!"

        encrypted_dek, encrypted_payload, metadata = crypto.encrypt_payload(
            test_resource.id, secret.id, synthetic_credential
        )

        from datetime import datetime, timezone

        from app.vault.domain import SecretVersion

        version = SecretVersion(
            id=uuid.uuid4(),
            secret_id=secret.id,
            encrypted_dek=encrypted_dek,
            encrypted_payload=encrypted_payload,
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
            created_by=admin_user.id,
        )
        secret.add_version(version)

        repo = SqlAlchemyVaultRepository(db.session)
        repo.save(secret)
        db.session.commit()

        # Setup default policy (ALLOW for testing)
        policy_allow = AccessPolicy(
            id=uuid.uuid4(),
            name="E2E Allow Policy",
            conditions={},
            requires_approval=False,
            effect=PolicyEffect.ALLOW,
            priority=100,
            enabled=True,
        )
        db.session.add(policy_allow)

        # Also setup ResourceAccessPolicy since the engine currently uses it (incorrectly)
        from app.resources.models import ResourceAccessPolicy

        res_policy = ResourceAccessPolicy(
            id=uuid.uuid4(),
            resource_id=test_resource.id,
            role_id=role_vault_read.id,
            approval_required=False,
        )
        db.session.add(res_policy)
        db.session.commit()

        print("E2E database seeded successfully.")


if __name__ == "__main__":
    seed()
