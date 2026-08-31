"""OpsForge Flask Application Factory.

Initializes the Flask application instance and boot procedures.
"""

import logging
import os

from flask import Flask

from app.checkout.routes import bp as checkout_bp
from app.platform.config import get_config
from app.platform.extensions import db, migrate
from app.platform.logging import init_logging
from app.routes import blueprint as api_bp
from app.utils.errors import register_error_handlers

__all__ = ["create_app"]


def create_app(validate_kms: bool = True, testing_bootstrap: bool = False) -> Flask:
    """Flask Application Factory function."""
    if os.environ.get("FLASK_SKIP_KMS_VALIDATION", "").lower() in (
        "true",
        "1",
        "yes",
    ) or os.environ.get("SKIP_KMS_VALIDATION", "").lower() in ("true", "1", "yes"):
        validate_kms = False

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
    # Models are imported to register metadata
    from app.audit import models as audit_models  # noqa: F401
    from app.checkout import models as checkout_models  # noqa: F401
    from app.compliance import models as compliance_models  # noqa: F401
    from app.jit_access import models as jit_access_models  # noqa: F401
    from app.notifications import models as notif_models  # noqa: F401
    from app.platform.extensions import limiter
    from app.policy_engine import models as policy_models  # noqa: F401
    from app.resources import models as resource_models  # noqa: F401
    from app.sessions import models as session_models  # noqa: F401
    from app.vault import models as vault_models  # noqa: F401
    from app.vault_lifecycle import models as vault_lifecycle_models  # noqa: F401

    if testing_bootstrap:
        from app.security.bootstrap.rbac_seed_service import seed_rbac
        from app.vault.bootstrap import seed_kms

        with app.app_context():
            db.drop_all()
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
                'relation "kms_configurations" does not exist',
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

    cors_resources = app.config.get("CORS_RESOURCES") or {r"/*": {"origins": "*"}}
    CORS(app, resources=cors_resources)

    # Register logging and Request ID middleware
    from app.platform.middleware import register_middleware

    register_middleware(app)

    # Register error handlers
    register_error_handlers(app)

    # Register API blueprint
    app.register_blueprint(api_bp)
    app.register_blueprint(checkout_bp)

    # Register CLI commands
    from app.cli.checkout_commands import register_commands as register_checkout
    from app.cli.rotation_commands import register_commands as register_rotation
    from app.cli.seed_commands import register_commands as register_seed
    from app.cli.token_commands import register_commands as register_tokens

    register_seed(app)
    register_tokens(app)
    register_rotation(app)
    register_checkout(app)

    # Register notification handlers
    from app.notifications.bootstrap import register_notification_handlers

    register_notification_handlers(app)

    return app
