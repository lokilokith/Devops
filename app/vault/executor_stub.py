# Stub implementation of credential executor for testing.
"""A deterministic test‑double used by the RotationWorker (future work).

It never performs any network I/O and returns opaque bytes on success.
The behaviour is driven by a mapping supplied at construction time:
    {resource_id: "success" | "retry" | "terminal"}
Missing resource ids result in ``can_execute`` => False.
"""

from __future__ import annotations

import uuid
from typing import Dict
from .executor import CredentialExecutor, ExecutionResult


class StubCredentialExecutor:
    """Deterministic stub executor.

    Parameters
    ----------
    behaviour_map: dict[uuid.UUID, str] | None
        Mapping of ``resource_id`` to mode.  Supported modes:
        * ``"success"`` – returns a fake encrypted blob.
        * ``"retry"`` – raises ``RuntimeError`` with a retryable message.
        * ``"terminal"`` – raises ``RuntimeError`` with a terminal message.
        If omitted, all resources default to ``"success"`` when ``can_execute``
        is True.
    """

    def __init__(self, behaviour_map: Dict[uuid.UUID, str] | None = None):
        self._behaviour: Dict[uuid.UUID, str] = behaviour_map or {}

    # ---------------------------------------------------------------------
    def can_execute(self, resource_id: uuid.UUID) -> bool:
        """Return ``True`` if the executor knows how to handle ``resource_id``.
        The check is purely in‑memory and does not perform I/O.
        """
        return resource_id in self._behaviour

    # ---------------------------------------------------------------------
    def execute(self, resource_id: uuid.UUID, current_secret: bytes) -> ExecutionResult:
        """Execute the rotation for ``resource_id``.

        Returns an ``ExecutionResult`` on success.  On failure a ``RuntimeError``
        with a generic message is raised – the message contains the word
        ``retryable`` for the retry mode and ``terminal`` for the terminal mode.
        No credential data is ever logged or included in the exception.
        """
        mode = self._behaviour.get(resource_id, "success")
        if mode == "success":
            # Produce a deterministic opaque payload – uuid4 ensures uniqueness.
            fake_blob = f"{resource_id}-{uuid.uuid4()}".encode()
            return {
                "new_secret_version": fake_blob,
                "metadata": {"generated_by": "stub"},
                "error": "",
            }
        if mode == "retry":
            raise RuntimeError("Transient error – retryable")
        # terminal failure
        raise RuntimeError("Permanent error – terminal")
