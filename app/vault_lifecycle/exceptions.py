"""Vault Lifecycle Exceptions."""

class VaultLifecycleError(Exception):
    """Base exception for Vault Lifecycle module."""
    pass

class PolicyNotFoundError(VaultLifecycleError):
    """Raised when a policy is not found."""
    pass

class PolicyValidationError(VaultLifecycleError):
    """Raised when policy data is invalid."""
    pass

class RotationNotPermittedError(VaultLifecycleError):
    """Raised when rotation is manually denied by policy evaluation."""
    pass
