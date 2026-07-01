"""OpsForge Production Configuration."""

import os
from app.config.base import BaseConfig


class ProductionConfig(BaseConfig):
    """Production Configuration settings."""

    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")


# Validate configuration only if it is the active environment config
if os.environ.get("APP_ENV", "development").lower() == "production":
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "Configuration Error: DATABASE_URL environment variable is missing. "
            "A valid PostgreSQL connection URL is required for production."
        )
