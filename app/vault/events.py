"""Vault Domain Events."""

from __future__ import annotations

from blinker import Namespace

vault_signals = Namespace()

# Domain Events MUST include a correlation_id in their payloads.
# Payload format:
# {
#     "event": "event_name",
#     "correlation_id": "...",
#     "secret_id": "...",
#     "actor_id": "...",
#     "timestamp": "...",
#     ...
# }

secret_created = vault_signals.signal("secret_created")
secret_accessed = vault_signals.signal("secret_accessed")
secret_access_denied = vault_signals.signal("secret_access_denied")
secret_rotated = vault_signals.signal("secret_rotated")
secret_disabled = vault_signals.signal("secret_disabled")
secret_deleted = vault_signals.signal("secret_deleted")

# Phase 2B.2 Rotation Lifecycle Events
secret_rotation_requested = vault_signals.signal("secret_rotation_requested")
secret_rotation_started = vault_signals.signal("secret_rotation_started")
secret_rotation_completed = vault_signals.signal("secret_rotation_completed")
secret_rotation_failed = vault_signals.signal("secret_rotation_failed")
