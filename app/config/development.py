"""OpsForge Development Configuration."""

import os
from app.config.base import BaseConfig


class DevelopmentConfig(BaseConfig):
    """Development Configuration settings."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
