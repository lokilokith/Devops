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


def create_app(validate_kms: bool = True, testing_bootstrap: bool = False) -> Flask:
    """Flask Application Factory function."""
    app = Flask(__name__)

    # Load configuration
    config_class = get_config()
    app.config.from_object(config_class)

    # Initialize structured console logging for the application-scoped logger
    init_logging(debug=app.config.get("DEBUG", False))


    opsforge_logger = logging.getLogger("opsforge")
    app.logger.handlers = opsforge_logger.handlers
    app.logger.setLevel(opsforge_logger.level)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    from app.extensions import limiter
    
    if testing_bootstrap:
        from app.vault.bootstrap import seed_kms
        from app.security.bootstrap.rbac_seed_service import seed_rbac
        with app.app_context():
            db.create_all()
            seed_kms()
            seed_rbac()

    if validate_kms:
        try:
            # Resolve the active KMS provider via factory within an app context
            from app.vault.kms_factory import KMSProviderFactory
            with app.app_context():
                KMSProviderFactory.resolve_active_provider(db.session)
        except Exception as e:
            # Missing KMS table indicates migrations not applied yet; skip validation.
            missing_indicators = [
                "relation \"kms_configurations\" does not exist",
                "no such table: kms_configurations",
            ]
            if any(msg in str(e) for msg in missing_indicators):
                app.logger.info("KMS validation skipped: migrations not applied yet.")
            else:
                # Any other error (e.g., no active config) should be fatal.
                app.logger.critical(f"Startup validation failed: {e}")
                raise RuntimeError(f"Startup validation failed: {e}") from e

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
    from app.cli.rotation_commands import register_commands as register_rotation

    register_seed(app)
    register_tokens(app)
    register_rotation(app)

    # Register notification handlers
    from app.notifications.bootstrap import register_notification_handlers

    register_notification_handlers(app)

    return app
