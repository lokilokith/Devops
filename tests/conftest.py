"""OpsForge Pytest Configuration and Fixtures.

Configures test environment variables and configures DB setups.
"""

import os

# Force testing environment config immediately on import
os.environ["APP_ENV"] = "testing"

import pytest
from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    """Establish scoped testing hooks and yield a Flask application context."""
    app = create_app()

    with app.app_context():
        # Build test schemas
        db.create_all()
        yield app
        # Tear down session and tables
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Returns a Flask application test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Returns a Flask application CLI test runner."""
    return app.test_cli_runner()
