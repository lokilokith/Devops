"""OpsForge Testing Configuration."""

from app.config.base import BaseConfig


class TestingConfig(BaseConfig):
    """Testing Configuration settings, targeting in-memory SQLite database."""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
