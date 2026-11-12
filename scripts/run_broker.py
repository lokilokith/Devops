"""Start the OpsForge SSH Broker for E2E testing.

Connects to the E2E database and listens for brokered SSH sessions.
Uses the same host key verification as production — no mocking.
"""

import asyncio
import logging
import os
import sys

import asyncssh

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure E2E database environment defaults are set before app initialization
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://e2e_user:e2e_password@localhost:5441/opsforge_e2e_db",
)
os.environ.setdefault("SECRET_KEY", "e2e_secret_key")
os.environ.setdefault("JWT_SECRET_KEY", "e2e_jwt_secret_key")
os.environ.setdefault(
    "VAULT_MASTER_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
)

from app import create_app
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.platform.extensions import db
from app.vault.credential_use import CredentialUseService
from app.vault.crypto import EncryptionService
from app.vault.kms_factory import KMSProviderFactory
from app.vault.repository import SqlAlchemyVaultRepository
from app.workers.ssh_broker import OpsForgeSSHBroker, start_expiry_monitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] Broker: %(message)s",
)
logger = logging.getLogger(__name__)

BROKER_HOST = os.environ.get("BROKER_HOST", "127.0.0.1")
BROKER_PORT = int(os.environ.get("BROKER_PORT", "2223"))

# Path to deterministic host key for the broker's own SSH server identity.
# If this file exists, the broker uses it as its server key (stable across restarts).
# Otherwise, it generates an ephemeral key.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
_BROKER_SERVER_KEY_PATH = os.path.join(
    _REPO_ROOT, "docker", "target", "broker_host_ed25519_key"
)


def create_broker_factory(app):
    """Return a callable that creates a new OpsForgeSSHBroker instance per connection."""

    def app_context_factory():
        return app.app_context()

    def factory():
        with app.app_context():
            kms = KMSProviderFactory.resolve_active_provider(db.session)
            enc_svc = EncryptionService(kms)
            secret_repo = SqlAlchemyVaultRepository(db.session)
            cred_use_svc = CredentialUseService(secret_repo, enc_svc)

            audit_repo = AuditRepository(db.session)
            audit_svc = AuditService(audit_repo)

        return OpsForgeSSHBroker(
            app_context=app_context_factory,
            audit_service=audit_svc,
            credential_use_service=cred_use_svc,
        )

    return factory


async def start_server():
    app = create_app(validate_kms=False, testing_bootstrap=False)

    # Generate or load the broker's server key
    if os.path.exists(_BROKER_SERVER_KEY_PATH):
        logger.info(f"Loading broker server key from {_BROKER_SERVER_KEY_PATH}")
        server_keys = [asyncssh.read_private_key(_BROKER_SERVER_KEY_PATH)]
    else:
        logger.info("Generating ephemeral broker server key")
        server_keys = [asyncssh.generate_private_key("ssh-ed25519")]
        # Save public key for test known_hosts
        pub_key_path = _BROKER_SERVER_KEY_PATH + ".pub"
        try:
            pub_key = server_keys[0].export_public_key().decode("utf-8").strip()
            with open(pub_key_path, "w") as f:
                f.write(pub_key + "\n")
            logger.info(f"Broker server public key saved to {pub_key_path}")
        except Exception as e:
            logger.warning(f"Could not save broker public key: {e}")

    factory = create_broker_factory(app)

    logger.info(f"Starting OpsForge SSH Broker on {BROKER_HOST}:{BROKER_PORT}...")

    server = await asyncssh.create_server(
        factory,
        host=BROKER_HOST,
        port=BROKER_PORT,
        server_host_keys=server_keys,
    )

    # Start the expiry monitor in the background
    def expiry_context():
        return app.app_context()

    asyncio.create_task(start_expiry_monitor(expiry_context))

    logger.info(f"Broker listening on {BROKER_HOST}:{BROKER_PORT}")
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(start_server())
