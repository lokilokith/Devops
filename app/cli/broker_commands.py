"""SSH Broker CLI Commands (Phase 11).

Provides the entrypoint for starting the OpsForge SSH Broker.
"""

import asyncio
import logging

import asyncssh
import click
from flask import current_app
from flask.cli import with_appcontext

from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.platform.extensions import db
from app.vault.credential_use import CredentialUseService
from app.vault.crypto import EncryptionService
from app.vault.kms_factory import KMSProviderFactory
from app.vault.repository import SqlAlchemyVaultRepository
from app.workers.ssh_broker import OpsForgeSSHBroker, start_expiry_monitor

logger = logging.getLogger(__name__)


async def run_broker_async(
    port: int, app_context, audit_service, credential_use_service
):
    """Run the AsyncSSH server and background tasks."""
    def server_factory():
        return OpsForgeSSHBroker(
            app_context=app_context,
            audit_service=audit_service,
            credential_use_service=credential_use_service,
        )

    # In a real environment, we'd load persistent host keys.
    # For prototype, we generate ephemeral host keys.
    server_keys = asyncssh.generate_private_key("ssh-ed25519")

    # Start the expiry monitor
    monitor_task = asyncio.create_task(start_expiry_monitor(app_context))

    try:
        logger.info(f"Starting OpsForge SSH Broker on port {port}")
        await asyncssh.listen(
            host="", port=port, server_host_keys=[server_keys], server_factory=server_factory
        )
        # Keep the event loop running
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Broker failed: {e}")
    finally:
        monitor_task.cancel()


@click.command("start")
@click.option("--port", default=2222, help="Port to listen on")
@with_appcontext
def start_broker_command(port: int):
    """Start the OpsForge SSH Broker endpoint."""
    click.echo(f"Initializing OpsForge SSH Broker on port {port}...")

    session = db.session

    audit_repo = AuditRepository(session)
    audit_service = AuditService(audit_repo)

    try:
        kms_provider = KMSProviderFactory.resolve_active_provider(session)
    except Exception as e:
        click.secho(f"Failed to resolve KMS provider: {e}", fg="red")
        raise click.Abort()

    encryption_service = EncryptionService(kms_provider)
    vault_repo = SqlAlchemyVaultRepository(session)
    credential_use_service = CredentialUseService(vault_repo, encryption_service)

    # We need to capture the flask app to spawn app_contexts in async code
    app = current_app._get_current_object()

    def app_context_factory():
        return app.app_context()

    try:
        asyncio.run(
            run_broker_async(
                port, app_context_factory, audit_service, credential_use_service
            )
        )
    except KeyboardInterrupt:
        click.echo("Broker shutting down.")


@click.group("broker")
def broker_group():
    """Commands for managing the OpsForge SSH Broker."""
    pass


def register_commands(app):
    """Register broker CLI commands."""
    broker_group.add_command(start_broker_command)
    app.cli.add_command(broker_group)
