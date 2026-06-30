"""OpsForge Production Configuration."""

import os
from app.config.base import BaseConfig
from app.utils.custom_exceptions import ConfigurationException


class ProductionConfig(BaseConfig):
    """Production Configuration settings."""

    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


# Validate configuration only if it is the active environment config
if os.environ.get("APP_ENV", "development").lower() == "production":
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ConfigurationException(
            "DATABASE_URL environment variable is missing. "
            "A valid PostgreSQL connection URL is required for production."
        )
    if not db_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        raise ConfigurationException(
            f"DATABASE_URL must target a PostgreSQL dialect in production, got: '{db_url}'"
        )
