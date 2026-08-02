"""OpsForge Testing Configuration."""

import os
import tempfile

from app.config.base import BaseConfig


class TestingConfig(BaseConfig):
    """Testing Configuration settings, targeting in-memory SQLite database."""

    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
        tempfile.gettempdir(), "opsforge_test.db"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {}
