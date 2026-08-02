"""OpsForge Production Configuration."""

import os

from app.config.base import BaseConfig


class ProductionConfig(BaseConfig):
    """Production Configuration settings."""

    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    # Enforce secrets
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if os.environ.get("APP_ENV", "").lower() == "production" and (
        not SECRET_KEY or SECRET_KEY == "default-dev-key"
    ):  # nosec - Checking for insecure default key
        raise RuntimeError("SECRET_KEY must be set securely in production.")

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    if os.environ.get("APP_ENV", "").lower() == "production" and (
        not JWT_SECRET_KEY
        or JWT_SECRET_KEY
        == "super-secret-default-key-at-least-32-bytes"  # nosec - Checking for insecure default key
    ):
        raise RuntimeError("JWT_SECRET_KEY must be set securely in production.")

    # Restrict wildcard and configure specific whitelisted origins in production
    allowed_origins = os.environ.get(
        "CORS_ALLOWED_ORIGINS", "https://opsforge.internal"
    ).split(",")
    CORS_RESOURCES = {
        r"/*": {"origins": [orig.strip() for orig in allowed_origins if orig.strip()]}
    }
