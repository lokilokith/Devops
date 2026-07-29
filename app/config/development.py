"""OpsForge Development Configuration."""

import os
import sys

from app.config.base import BaseConfig


class DevelopmentConfig(BaseConfig):
    """Development Configuration settings."""

    DEBUG = True
    
    _db_url = os.environ.get("DATABASE_URL")
    if _db_url and _db_url.startswith("sqlite:///"):
        # Make the SQLite database path absolute relative to the project root
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        db_file = _db_url.replace("sqlite:///", "")
        
        # If it's a relative path, resolve it relative to the instance folder for Flask-SQLAlchemy 3+ compatibility
        if not os.path.isabs(db_file):
            _db_url = f"sqlite:///{os.path.join(project_root, 'instance', db_file)}"
            
    SQLALCHEMY_DATABASE_URI = _db_url

