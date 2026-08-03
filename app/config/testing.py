"""OpsForge Testing Configuration."""

import os
import tempfile

from app.config.base import BaseConfig


class TestingConfig(BaseConfig):
    """Testing Configuration settings, targeting in-memory SQLite database."""

    TESTING = True
    DEBUG = True
    _db_url = os.environ.get("DATABASE_URL")
    if _db_url:
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
            tempfile.gettempdir(), "opsforge_test.db"
        )
    SQLALCHEMY_ENGINE_OPTIONS = {}
