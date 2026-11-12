"""Checkout domain exceptions."""


class CheckoutError(Exception):
    """Base exception for Checkout errors."""

    pass


class InvalidCheckoutStateError(CheckoutError):
    """Raised when the state of the lease or secret prevents checkout operations."""

    pass


class LeaseNotFoundError(CheckoutError):
    """Raised when a requested lease is not found."""

    pass


class UnauthorizedCheckoutError(CheckoutError):
    """Raised when a user is not authorized for a checkout operation."""

    pass


class PolicyDeniedError(CheckoutError):
    """Raised when the Policy Engine explicitly denies a checkout request."""

    pass
