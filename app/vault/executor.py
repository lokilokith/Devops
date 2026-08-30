# Executor abstraction for credential rotation
"""Credential executor abstraction.

Defines a protocol that separates domain orchestration from the concrete
implementation that talks to external systems (SSH, DB, cloud APIs, etc.).
All operations are opaque – the executor never logs or propagates raw
credential bytes.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict
from uuid import UUID


class ExecutionResult(TypedDict, total=False):
    """Result of a credential rotation execution.

    * ``new_secret_version`` – opaque encrypted bytes that will be stored as
      the new secret payload.
    * ``metadata`` – optional auxiliary information (e.g., timestamps,
      executor‑specific details).  Values must be JSON‑serialisable.
    * ``error`` – optional error message for retryable failures; the caller
      should treat a non‑empty ``error`` as a transient problem.
    """

    new_secret_version: bytes
    metadata: dict[str, Any]
    error: str


class CredentialExecutor(Protocol):
    """Protocol for rotating a secret's underlying credential.

    Implementations must be **purely infrastructural** – they must not depend
    on Flask, SQLAlchemy models or any domain services.  All inputs and
    outputs are treated as opaque bytes.
    """

    def can_execute(self, resource_id: UUID) -> bool:
        """Return ``True`` if this executor knows how to rotate the given
        ``resource_id``.  The check must be deterministic and must not perform
        any network I/O.
        """
        ...

    def execute(self, resource_id: UUID, current_secret: bytes) -> ExecutionResult:
        """Perform the rotation for ``resource_id``.

        * ``current_secret`` is the **opaque** encrypted payload currently
          stored for the secret – it must never be logged or included in any
          exception messages.
        * The method may raise ``RuntimeError`` with a generic message for
          unrecoverable (terminal) failures.  For retryable failures the
          implementation should raise ``RuntimeError`` with a message that
          contains the word ``retryable`` (case‑insensitive) – callers can use
          this to decide on back‑off/retry logic.
        * The returned ``ExecutionResult`` must contain either a
          ``new_secret_version`` (bytes) **or** an ``error`` string.  It must
          never contain the raw ``current_secret``.
        """
        ...
