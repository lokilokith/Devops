# app/vault/bootstrap.py
"""Bootstrap utilities for the Vault module.

Provides a `seed_kms` function that creates a default KMS configuration
used by the `seed-kms` CLI command.
"""

from app.shared.database import db
from app.vault.models import KMSConfiguration, KMSProviderType
from sqlalchemy.exc import IntegrityError

def seed_kms():
    """Create a default active KMS configuration.

    The configuration uses the ``LOCAL`` provider and reads the master key
    from the ``VAULT_MASTER_KEY`` environment variable. If a configuration
    already exists, the function logs a warning and leaves the existing
    record untouched.
    """
    from flask import current_app
    logger = current_app.logger

    # Check if an active configuration already exists
    existing = (
        db.session.query(KMSConfiguration)
        .filter(KMSConfiguration.is_active.is_(True))
        .first()
    )
    if existing:
        logger.info("KMS configuration already exists, skipping seed.")
        return

    cfg = KMSConfiguration(
        provider_type=KMSProviderType.LOCAL,
        kms_endpoint=None,
        kms_key_id="default-local-key",
        is_active=True,
    )
    db.session.add(cfg)
    try:
        db.session.commit()
        logger.info("Default LOCAL KMS configuration seeded.")
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Failed to seed KMS configuration: {e}")
        raise
