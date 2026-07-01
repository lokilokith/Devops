"""OpsForge Base Configuration."""

import os


class BaseConfig:
    """Base Configuration containing shared settings across environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "default-dev-key")
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
