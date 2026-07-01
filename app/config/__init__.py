"""OpsForge Configuration Loader.

Loads the environment config class dynamically after strict environment validation.
"""

import os


def get_config():
    """Gets the configuration class associated with the active APP_ENV."""
    env = os.environ.get("APP_ENV", "development").lower()

    if env not in ["development", "testing", "production"]:
        raw_env = os.environ.get("APP_ENV")
        raise ValueError(
            f'Unsupported APP_ENV "{raw_env}". '
            "Supported values are: 'development', 'testing', 'production'"
        )

    if env == "testing":
        from app.config.testing import TestingConfig

        return TestingConfig
    elif env == "production":
        from app.config.production import ProductionConfig

        return ProductionConfig
    else:
        from app.config.development import DevelopmentConfig

        return DevelopmentConfig
