"""OpsForge Production Configuration."""

import os
from app.config.base import BaseConfig


class ProductionConfig(BaseConfig):
    """Production Configuration settings."""

    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    # Restrict wildcard and configure specific whitelisted origins in production
    allowed_origins = os.environ.get(
        "CORS_ALLOWED_ORIGINS", "https://opsforge.internal"
    ).split(",")
    CORS_RESOURCES = {
        r"/*": {"origins": [orig.strip() for orig in allowed_origins if orig.strip()]}
    }
