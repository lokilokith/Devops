"""Execution Plane Exception Hierarchy.

Explicit, typed exceptions for Execution Plane operations.
All exception classes implement safe string formatting to prevent accidental
leakage of secrets, private keys, or credential material into logs, traces, or responses.
"""

from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

# Common secret pattern keywords for defensive sanitization
_SENSITIVE_KEYWORD_RE = re.compile(
    r"(?i)([\w_-]*(?:password|secret|token|key|credential|payload|bearer|private)[\w_-]*)\s*[:=]\s*(\S+)"
)


def sanitize_error_message(message: str) -> str:
    """Defensively sanitize a message string to remove any credential patterns."""
    if not message:
        return ""
    # Redact obvious key=value or key: value secret patterns
    sanitized = _SENSITIVE_KEYWORD_RE.sub(r"\1=[REDACTED]", message)
    return sanitized


class ExecutionError(Exception):
    """Base exception for all Execution Plane errors."""

    def __init__(
        self,
        message: str,
        resource_id: Optional[UUID] = None,
        execution_id: Optional[UUID] = None,
        details: Optional[dict] = None,
    ) -> None:
        self.raw_message = message
        self.sanitized_message = sanitize_error_message(message)
        self.resource_id = resource_id
        self.execution_id = execution_id
        self.details = details or {}
        super().__init__(self.sanitized_message)


class TargetAuthenticationError(ExecutionError):
    """Raised when authentication to the target fails (e.g. invalid key, host-key mismatch)."""


class TargetAuthorizationError(ExecutionError):
    """Raised when target-side privilege elevation or authorization is denied."""


class ExecutionTimeoutError(ExecutionError):
    """Raised when a target execution operation exceeds its allocated timeout."""


class TransportError(ExecutionError):
    """Raised when network connectivity or socket communication with target fails."""


class TargetExecutionError(ExecutionError):
    """Raised when a target command or helper executable returns a non-zero exit status."""


class VerificationFailureError(ExecutionError):
    """Raised when post-execution verification indicates target state does not match expected outcome."""


class SecurityUncertaintyError(ExecutionError):
    """Raised when an operation was interrupted or failed and target state cannot be confidently verified.

    Represents the highest severity execution error. Rollback was attempted but could not be confirmed.
    """


class InvalidExecutionContextError(ExecutionError):
    """Raised when an execution request lacks required authorization context or is malformed."""
