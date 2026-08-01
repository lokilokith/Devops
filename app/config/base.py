"""OpsForge Base Configuration."""

import os


class BaseConfig:
    """Base Configuration containing shared settings across environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "default-dev-key")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "super-secret-default-key-at-least-32-bytes")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RESTX_MASK_SWAGGER = False
    CORS_RESOURCES = {
        r"/*": {
            "origins": [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:5000",
                "http://127.0.0.1:5000",
            ]
        }
    }

