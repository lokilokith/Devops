"""OpsForge Configuration Loader.

Loads the environment config class dynamically to prevent side-effects from inactive environments.
"""

import os


def get_config():
    """Gets the configuration class associated with the active APP_ENV."""
    env = os.environ.get("APP_ENV", "development").lower()

    if env == "testing":
        from app.config.testing import TestingConfig

        return TestingConfig
    elif env == "production":
        from app.config.production import ProductionConfig

        return ProductionConfig
    else:
        from app.config.development import DevelopmentConfig

        return DevelopmentConfig
