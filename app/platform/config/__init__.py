"""Platform configuration entrypoints."""

from app.config import get_config
from app.config.base import BaseConfig
from app.config.development import DevelopmentConfig
from app.config.production import ProductionConfig
from app.config.testing import TestingConfig

__all__ = [
    "get_config",
    "BaseConfig",
    "DevelopmentConfig",
    "ProductionConfig",
    "TestingConfig",
]
