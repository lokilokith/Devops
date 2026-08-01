"""OpsForge Configuration Loader.

Loads the environment config class dynamically after strict environment validation.
"""

import os

from app.utils.exceptions import ConfigurationException


def get_config():
    """Get config class for active APP_ENV after validation."""
    env = os.environ.get("APP_ENV")
    if not env:
        raise ConfigurationException(
            "Configuration Error: APP_ENV environment variable is missing. "
            "Please specify one of: 'development', 'testing', 'production'."
        )

    env_lower = env.lower()
    allowed_envs = ["development", "testing", "production"]
    if env_lower not in allowed_envs:
        raise ConfigurationException(
            f"Configuration Error: Unsupported APP_ENV '{env}'. "
            f"Supported environments are: {', '.join(allowed_envs)}."
        )

    # Validate secret key for development and production
    secret_key = os.environ.get("SECRET_KEY")
    if env_lower in ["development", "production"] and not secret_key:
        raise ConfigurationException(
            "Configuration Error: SECRET_KEY environment variable is missing. "
            "A secure secret key is required for execution"
            " in development and production environments."
        )

    # Validate database URL for development and production
    db_url = os.environ.get("DATABASE_URL")
    if env_lower in ["development", "production"] and not db_url:
        raise ConfigurationException(
            "Configuration Error: DATABASE_URL environment variable is missing. "
            "A valid database connection URL is required"
            " for execution in development and production"
            " environments."
        )

    # Validate JWT secret key for production
    jwt_secret_key = os.environ.get("JWT_SECRET_KEY")
    if env_lower == "production" and not jwt_secret_key:
        raise ConfigurationException(
            "Configuration Error: JWT_SECRET_KEY environment variable is missing. "
            "A secure JWT secret key is required for execution"
            " in production environments."
        )

    if env_lower == "testing":
        from app.config.testing import TestingConfig

        return TestingConfig
    elif env_lower == "production":
        from app.config.production import ProductionConfig

        return ProductionConfig
    else:
        from app.config.development import DevelopmentConfig

        return DevelopmentConfig
