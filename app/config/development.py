"""OpsForge Development Configuration."""

import os
from app.config.base import BaseConfig
from app.utils.custom_exceptions import ConfigurationException


class DevelopmentConfig(BaseConfig):
    """Development Configuration settings."""

    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


# Validate configuration only if it is the active environment config
if os.environ.get("APP_ENV", "development").lower() == "development":
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ConfigurationException(
            "DATABASE_URL environment variable is missing. "
            "A valid PostgreSQL connection URL is required for development."
        )
    if not db_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise ConfigurationException(
            f"DATABASE_URL must target a PostgreSQL dialect, got: '{db_url}'"
        )
