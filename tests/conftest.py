"""OpsForge Pytest Configurations & Fixtures."""

import os
import pytest
from app import create_app
from app.extensions import db


@pytest.fixture(scope="session", autouse=True)
def set_testing_env():
    """Forces APP_ENV to testing for all test executions."""
    os.environ["APP_ENV"] = "testing"


@pytest.fixture
def app():
    """Initializes the Flask application under a testing context."""
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    """Provides a Flask test client context."""
    return app.test_client()


@pytest.fixture
def db_session(app):
    """Provides an isolated database session transaction."""
    yield db.session
    db.session.rollback()
    db.session.remove()
