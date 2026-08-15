"""CLI commands for Credential Checkout."""

import click
from flask.cli import with_appcontext
from uuid import UUID

from app.platform.extensions import db
from app.checkout.routes import get_checkout_service
from app.workers.expiration_worker import run_expiration_job


@click.group("checkout")
def checkout_cli():
    """Manage Credential Checkouts."""
    pass


@checkout_cli.command("lease")
@click.argument("user_id")
@click.argument("access_request_id")
@with_appcontext
def checkout_credential(user_id, access_request_id):
    """Checkout a credential (ACTIVE -> CHECKED_OUT)."""
    service = get_checkout_service()
    try:
        plaintext = service.checkout(UUID(user_id), UUID(access_request_id))
        click.echo("Checkout successful.")
        click.echo(f"Credential: {plaintext.decode('utf-8')}")
    except Exception as e:
        click.secho(f"Checkout failed: {e}", fg="red")


@checkout_cli.command("checkin")
@click.argument("user_id")
@click.argument("lease_id")
@with_appcontext
def checkin_credential(user_id, lease_id):
    """Check-in an actively leased credential."""
    service = get_checkout_service()
    try:
        service.checkin(UUID(user_id), UUID(lease_id))
        click.echo("Check-in successful. Secret scheduled for rotation.")
    except Exception as e:
        click.secho(f"Check-in failed: {e}", fg="red")


@checkout_cli.command("process-expirations")
@with_appcontext
def process_expirations_cmd():
    """Process all expired leases via ExpirationWorker."""
    service = get_checkout_service()
    try:
        result = run_expiration_job(db.session, service)
        click.echo(f"Run ID: {result['run_id']}")
        click.echo(f"Processed {result['succeeded']} of {result['attempted']} expired leases.")
        if result['failed'] > 0:
            click.echo(f"Failed: {result['failed']}")
    except Exception as e:
        click.secho(f"Expiration processing failed: {e}", fg="red")


def register_commands(app):
    """Register checkout CLI commands with the Flask app."""
    app.cli.add_command(checkout_cli)
