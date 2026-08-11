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

    # Validate Vault Master Key at startup
    try:
        from app.vault.crypto import MasterKeyProvider
        
        # Instantiate provider to trigger key validations
        # The concrete implementation LocalEnvironmentKeyProvider will check VAULT_MASTER_KEY
        from app.vault.crypto import LocalEnvironmentKeyProvider
        LocalEnvironmentKeyProvider()
    except ValueError as e:
        app.logger.critical(f"Startup validation failed: {e}")
        raise RuntimeError(f"Startup validation failed: {e}") from e

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    from app.extensions import limiter

    limiter.init_app(app)

    # Initialize CORS
    from flask_cors import CORS

    CORS(app, resources=app.config.get("CORS_RESOURCES"))

    # Register logging and Request ID middleware
    from app.platform.middleware import register_middleware

    register_middleware(app)

    # Models are imported at module level and exported via __all__ to register metadata
    from app.audit import models as audit_models
    from app.notifications import models as notif_models
    from app.vault import models as vault_models
    from app.sessions import models as session_models
    from app.policy_engine import models as policy_models
    from app.vault_lifecycle import models as vault_lifecycle_models
    from app.compliance import models as compliance_models
    from app.jit_access import models as jit_access_models

    # Register error handlers
    register_error_handlers(app)

    # Register API blueprint
    app.register_blueprint(api_bp)

    # Register CLI commands
    from app.cli.seed_commands import register_commands as register_seed
    from app.cli.token_commands import register_commands as register_tokens

    register_seed(app)
    register_tokens(app)

    # Register notification handlers
    from app.notifications.bootstrap import register_notification_handlers

    register_notification_handlers(app)

    return app
