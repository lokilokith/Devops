"""OpsForge Base Configuration."""

import os


class BaseConfig:
    """Base Configuration containing shared configurations across environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "default-dev-key")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RESTX_MASK_SWAGGER = True
