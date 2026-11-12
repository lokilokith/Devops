import os
import sys
import time
import logging

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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

from app.platform.extensions import db
from app import create_app
from app.workers.jit_expiry_worker import JITExpiryWorker
from app.jit_access.service import JITAccessService
from app.jit_access.repository import JITAccessRepository
from app.audit.service import AuditService
from app.audit.repository import AuditRepository
from app.execution.executor import TargetExecutor
from app.execution.ssh_executor import SSHTargetExecutor, SSHExecutionConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] Worker: %(message)s')

def run_worker():
    app = create_app()
    with app.app_context():
        from unittest.mock import MagicMock
        from app.platform.extensions import db
        from app.execution.ssh_executor import SSHTargetExecutor, SSHExecutionConfig
        from app.execution.host_identity import HostKeyVerifier
        from app.resources.repository import ResourcesRepository
        from app.vault.repository import SqlAlchemyVaultRepository
        from app.vault.crypto import EncryptionService
        from app.vault.kms_factory import KMSProviderFactory

        repo = JITAccessRepository(db.session)
        audit_repo = AuditRepository(db.session)
        audit_service = AuditService(audit_repo)

        # Mocks for unused dependencies during worker revocation
        mock_ar = MagicMock()
        mock_policy = MagicMock()
        mock_auth = MagicMock()

        service = JITAccessService(
            repository=repo,
            access_request_service=mock_ar,
            policy_service=mock_policy,
            audit_service=audit_service,
            auth_service=mock_auth,
            session=db.session
        )

        def _resolver(rid):
            return ResourcesRepository(db.session).get_by_id(rid)

        executor_config = SSHExecutionConfig(allow_loopback=True, allowed_ports={22, 2222})
        executor = SSHTargetExecutor(
            config=executor_config,
            host_key_verifier=HostKeyVerifier(),
            resource_resolver=_resolver
        )

        # Load the mock bootstrap credential for tests if real isn't present
        from app.vault.repository import SqlAlchemyVaultRepository
        from app.vault.crypto import EncryptionService
        from app.vault.kms_factory import KMSProviderFactory

        vault_repo = SqlAlchemyVaultRepository(db.session)
        kms = KMSProviderFactory.resolve_active_provider(db.session)
        crypto = EncryptionService(kms)

        # Find the E2E disposable target resource
        res_repo = ResourcesRepository(db.session)
        target_res = res_repo.get_by_code("E2E_DISPOSABLE_TARGET")

        bootstrap_credential = None
        if target_res:
            secret = vault_repo.find_by_resource(target_res.id)
            if secret and secret.current_version:
                av = secret.current_version
                bootstrap_credential = crypto.decrypt_payload(
                    target_res.id, secret.id,
                    av.encrypted_dek, av.encrypted_payload, av.metadata
                )

        worker = JITExpiryWorker(
            service=service,
            audit_service=audit_service,
            executor=executor,
            bootstrap_credential=bootstrap_credential,
            worker_id="e2e_day4_worker_1"
        )

        logging.info("Starting continuous E2E worker loop...")

        try:
            while True:
                # Expire active grants that have timed out
                expired_results = worker.process_expired_grants()
                if expired_results:
                    logging.info(f"Processed {len(expired_results)} expired grants.")

                # Process interrupted revocations (like manual terminations from UI)
                revocation_results = worker.process_interrupted_revocations()
                if revocation_results:
                    logging.info(f"Recovered {len(revocation_results)} interrupted revocations.")

                # Small sleep to prevent tight loop
                time.sleep(2)
        except KeyboardInterrupt:
            logging.info("Worker loop stopped by KeyboardInterrupt.")

if __name__ == "__main__":
    run_worker()
