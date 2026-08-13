import logging
from datetime import datetime, timezone
import click
from flask.cli import with_appcontext

from app.platform.extensions import db
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.vault.kms_factory import KMSProviderFactory
from app.vault.crypto import EncryptionService
from app.vault_lifecycle.repository import SecretRotationPolicyRepository
from app.vault_lifecycle.service import VaultLifecycleService
from app.vault.executor_registry import ExecutorRegistry
from app.workers.rotation_worker import run_rotation_job, _PrivilegedAuthorizationService

logger = logging.getLogger(__name__)


@click.command("rotate-secrets")
@with_appcontext
def rotate_secrets_command():
    """Manually dispatch the credential rotation background job."""
    click.echo(f"[{datetime.now(timezone.utc).isoformat()}] Starting rotation dispatch...")

    try:
        # 1. Database session
        session = db.session

        # 2. Audit service
        audit_repo = AuditRepository(session)
        audit_service = AuditService(audit_repo)

        # 3. Encryption service (via certified KMS factory)
        try:
            kms_provider = KMSProviderFactory.resolve_active_provider(session)
        except Exception as e:
            click.secho(f"Failed to resolve KMS provider: {e}", fg="red")
            raise click.Abort()

        encryption_service = EncryptionService(kms_provider)

        # 4. Lifecycle service (using privileged authz for background workers)
        privileged_authz = _PrivilegedAuthorizationService()
        lifecycle_repo = SecretRotationPolicyRepository(session)
        lifecycle_service = VaultLifecycleService(
            repository=lifecycle_repo,
            audit_service=audit_service,
            authz_service=privileged_authz,
            session=session,
        )

        # 5. Executor registry
        executor_registry = ExecutorRegistry()

        # Execute
        result = run_rotation_job(
            session=session,
            audit_service=audit_service,
            encryption_service=encryption_service,
            lifecycle_service=lifecycle_service,
            executor_registry=executor_registry,
        )

        click.secho("Rotation job completed.", fg="green")
        click.echo(f"Attempted:  {result.get('attempted', 0)}")
        click.echo(f"Succeeded:  {result.get('succeeded', 0)}")
        click.echo(f"Retryable:  {result.get('retryable', 0) if 'retryable' in result else 0}")
        click.echo(f"Terminal:   {result.get('failed', 0)}")
        click.echo(f"Skipped:    {result.get('skipped', 0)}")

    except click.Abort:
        raise
    except Exception as e:
        logger.error(f"Rotation CLI dispatch failed: {e}")
        click.secho(f"Rotation CLI dispatch failed unexpectedly.", fg="red")
        raise click.Abort()


def register_commands(app):
    """Register CLI commands to the application."""
    app.cli.add_command(rotate_secrets_command)
