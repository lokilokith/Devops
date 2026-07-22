"""OpsForge Flask Application Factory.

Initializes the Flask application instance and boot procedures.
"""

import logging

from flask import Flask

from app.platform.config import get_config
from app.platform.extensions import db, migrate
from app.platform.logging import init_logging
from app.routes import blueprint as api_bp
from app.utils.errors import register_error_handlers

__all__ = ["create_app"]


def create_app() -> Flask:
    """Flask Application Factory function."""
    app = Flask(__name__)

    # Load configuration
    config_class = get_config()
    app.config.from_object(config_class)

    # Initialize structured console logging for the application-scoped logger
    init_logging(debug=app.config.get("DEBUG", False))

    # Direct Flask logger to use the same handlers and level as the 'opsforge' logger
    opsforge_logger = logging.getLogger("opsforge")
    app.logger.handlers = opsforge_logger.handlers
    app.logger.setLevel(opsforge_logger.level)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Initialize CORS
    from flask_cors import CORS

    CORS(app, resources=app.config.get("CORS_RESOURCES"))

    # Register logging and Request ID middleware
    from app.platform.middleware import register_middleware

    register_middleware(app)

    # Models are imported at module level and exported via __all__ to register metadata

    # Register error handlers
    register_error_handlers(app)

    # Register API blueprint
    app.register_blueprint(api_bp)

    return app

