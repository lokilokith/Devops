import os
import sys
from datetime import datetime, timedelta, timezone

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.platform.extensions import db
from app import create_app
from app.models.user import User, Role
from app.models.resource import Resource
from app.models.target_account_binding import TargetAccountBinding, TargetAccountBindingStatus
from app.models.jit_access import JITAccessGrant, JITGrantStatus, AccessRequest, AccessRequestStatus
from app.auth.password import hash_password
from app.vault.domain import SecretFactory, SecretVersion
from app.vault.crypto import LocalKMSProvider, EncryptionService
from app.vault.repository import SecretRepository
from app.vault.bootstrap import seed_kms
from datetime import datetime, timezone
import uuid

def seed_e2e_data():
    app = create_app(validate_kms=False)
    with app.app_context():
        print("Ensuring database schema exists...")
        db.create_all()

        print("Seeding KMS...")
        seed_kms()

        print("Cleaning up old Day 4 E2E data...")
        JITAccessGrant.query.filter(JITAccessGrant.command_set_id.in_(["day4_cmd", "day4_cmd_b"])).delete(synchronize_session=False)
        AccessRequest.query.filter(AccessRequest.justification.like("Day 4 E2E%")).delete(synchronize_session=False)
        TargetAccountBinding.query.filter_by(target_os_username="target_e2e_user").delete(synchronize_session=False)
        Resource.query.filter_by(name="opsforge-disposable-target").delete(synchronize_session=False)
        User.query.filter_by(email="e2e_a@example.com").delete(synchronize_session=False)
        User.query.filter_by(email="e2e_b@example.com").delete(synchronize_session=False)
        db.session.commit()

        # Seed Users
        admin_role = Role.query.filter_by(name="Admin").first()
        if not admin_role:
            admin_role = Role(name="Admin", permissions=["vault:read", "vault:write", "sessions:read", "sessions:write"])
            db.session.add(admin_role)

        user_a = User(
            email="e2e_a@example.com",
            password_hash=hash_password("password_a"),
            is_active=True,
            role=admin_role
        )
        user_b = User(
            email="e2e_b@example.com",
            password_hash=hash_password("password_b"),
            is_active=True,
            role=admin_role
        )
        db.session.add_all([user_a, user_b])
        db.session.flush()

        # Seed Resource
        resource = Resource(
            name="opsforge-disposable-target",
            description="Day 4 Disposable Target",
            type="server",
            metadata_json={"host": "127.0.0.1", "port": 2222}
        )
        db.session.add(resource)
        db.session.flush()

        # Seed Vault Secret (The opsforge-svc private key for the disposable target)
        kms = LocalKMSProvider()
        enc_service = EncryptionService(kms)

        target_key_path = os.path.join(os.path.dirname(__file__), '../docker/target/id_ed25519_opsforge_svc')
        with open(target_key_path, 'rb') as f:
            real_key_data = f.read()

        secret_id = uuid.uuid4()
        encrypted_payload, encrypted_dek, metadata = enc_service.encrypt_payload(secret_id, resource.id, real_key_data)

        secret = SecretFactory.create_new_secret(resource_id=resource.id)
        # Override the random ID with our known ID so we can match it
        secret.id = secret_id

        version = SecretVersion(
            id=uuid.uuid4(),
            secret_id=secret.id,
            encrypted_dek=encrypted_dek,
            encrypted_payload=encrypted_payload,
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
            created_by=user_a.id
        )
        secret.add_version(version)

        # Save secret using repo
        vault_repo = SecretRepository(db.session)
        vault_repo.save(secret)
        db.session.commit()

        # Seed Target Account Binding
        binding = TargetAccountBinding(
            control_plane_user_id=user_a.id,
            resource_id=resource.id,
            target_os_username="opsforge-svc", # Must match the user in target container
            ssh_credential_id=secret.id,
            status=TargetAccountBindingStatus.ACTIVE
        )
        db.session.add(binding)
        db.session.flush()

        # Seed Access Request
        req_a = AccessRequest(
            requester_id=user_a.id,
            resource_id=resource.id,
            role_id=admin_role.id,
            justification="Day 4 E2E Session A",
            status=AccessRequestStatus.APPROVED,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        db.session.add(req_a)
        db.session.flush()

        # Seed JIT Grant (PENDING - Ready for Activation)
        grant_a = JITAccessGrant(
            user_id=user_a.id,
            role_id=admin_role.id,
            resource_id=resource.id,
            target_account_binding_id=binding.id,
            command_set_id="day4_cmd",
            approval_request_id=req_a.id,
            status=JITGrantStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        db.session.add(grant_a)

        db.session.commit()
        print(f"Data seeded successfully. User A ID: {user_a.id}, Grant A ID: {grant_a.id}")

if __name__ == "__main__":
    seed_e2e_data()
