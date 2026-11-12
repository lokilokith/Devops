import click
from flask.cli import with_appcontext

from app.security.bootstrap import seed_rbac
from app.security.bootstrap.rbac_seed_service import RBACSeedError
from app.vault.bootstrap import seed_kms


@click.command("seed-rbac")
@with_appcontext
def seed_rbac_command():
    """Seed the database with default RBAC configuration."""
    try:
        seed_rbac()
    except RBACSeedError as e:
        click.secho(f"Error: {e}", fg="red")
        raise click.Abort()
    except Exception as e:
        click.secho(f"Unexpected error: {e}", fg="red")
        raise click.Abort()


@click.command("seed-kms")
@with_appcontext
def seed_kms_command():
    """Seed the database with default KMS configuration."""
    try:
        seed_kms()
    except Exception as e:
        click.secho(f"Unexpected error: {e}", fg="red")
        raise click.Abort()


def register_commands(app):
    """Register CLI commands to the application."""
    app.cli.add_command(seed_rbac_command)
    app.cli.add_command(seed_kms_command)
