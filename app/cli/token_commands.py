import click
from flask.cli import with_appcontext

from app.auth.service import AuthService
from app.identity.repository import IdentityRepository
from app.platform.extensions import db


@click.command("purge-revoked-tokens")
@with_appcontext
def purge_revoked_tokens_command():
    """Purge expired revoked tokens from the database."""
    try:
        # UserRepo is needed for AuthService constructor
        user_repo = IdentityRepository(db.session)
        service = AuthService(user_repo)

        deleted_count = service.purge_expired_revoked_tokens()
        click.secho(
            f"Successfully purged {deleted_count} expired revoked token(s).", fg="green"
        )
    except Exception as e:
        click.secho(f"Error purging tokens: {e}", fg="red")
        raise click.Abort()


def register_commands(app):
    """Register CLI commands to the application."""
    app.cli.add_command(purge_revoked_tokens_command)
