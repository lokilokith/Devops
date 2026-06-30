"""OpsForge Flask Application Factory.

Bootstraps the Flask application, loads configurations, configures logging,
initializes extensions, and registers blueprints.
"""

from flask import Flask
from app.config import get_config
from app.extensions import db, migrate
from app.logging import setup_logging
from app.routes import blueprint as api_bp
from app.routes import api as restx_api
from app.utils.errors import register_error_handlers


def create_app() -> Flask:
    """Flask Application Factory function."""
    app = Flask(__name__)

    # Load environment configuration class
    config_class = get_config()
    app.config.from_object(config_class)

    # Initialize centralized console logging
    setup_logging(debug=app.config.get("DEBUG", False))

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register global API error handlers
    register_error_handlers(restx_api)

    # Register routing blueprint containing namespaces
    app.register_blueprint(api_bp)

    return app
