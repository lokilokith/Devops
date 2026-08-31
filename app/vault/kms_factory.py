"""Vault KMS Provider Factory.

Provides a deterministic way to resolve the active KMS provider based on the
KMSConfiguration stored in the database.

The factory enforces a strict fail‑closed contract:
- No active configuration → KMSConfigurationError
- Disabled configuration (i.e., not active) → KMSConfigurationError
- Supported provider (currently only LOCAL) → appropriate provider instance
- Unsupported provider → UnsupportedKMSProviderError
- No implicit fallback to a local provider when configuration is missing.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, scoped_session

from app.vault.crypto import (
    KMSConfigurationError,
    LocalKMSProvider,
    UnsupportedKMSProviderError,
)
from app.vault.models import KMSConfiguration, KMSProviderType


class KMSProviderFactory:
    """Factory to resolve the active KMS provider."""

    @staticmethod
    def resolve_active_provider(session: Session | scoped_session):
        """Return an instantiated KMS provider according to the active config.

        Args:
            session: SQLAlchemy session bound to the current request.

        Returns:
            An object implementing ``KMSProvider`` (e.g., ``LocalKMSProvider``).

        Raises:
            KMSConfigurationError: When there is no active configuration or the
                configuration is disabled.
            UnsupportedKMSProviderError: When the provider_type is not supported
                by the application.
        """
        # Fetch the active configuration. ``is_active`` must be true.
        config: KMSConfiguration | None = (
            session.query(KMSConfiguration).filter_by(is_active=True).one_or_none()
        )

        if config is None:
            raise KMSConfigurationError("No active KMS configuration found")

        if config.provider_type == KMSProviderType.LOCAL:
            return LocalKMSProvider()

        raise UnsupportedKMSProviderError(
            f"Unsupported KMS provider type: {config.provider_type}"
        )
