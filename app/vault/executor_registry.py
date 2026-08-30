# Registry for credential executors.
"""A lightweight registry that holds a list of ``CredentialExecutor``
implementations and selects the appropriate one for a given resource.

The registry does **not** contain any retry, audit or rotation logic – it
simply provides ``get_executor`` which returns the first executor whose
``can_execute`` returns ``True``.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from .executor import CredentialExecutor
from .executor_stub import StubCredentialExecutor


class ExecutorRegistry:
    """Holds registered executors and selects a capable executor.

    By default a single ``StubCredentialExecutor`` is registered.  Production
    code can instantiate the registry with additional concrete executors.
    """

    def __init__(self, executors: List[CredentialExecutor] | None = None):
        # If the caller supplies executors we honour them; otherwise we fall back
        # to a stub that can be configured later.
        self._executors: List[CredentialExecutor] = executors or [
            StubCredentialExecutor()
        ]

    def get_executor(self, resource_id: UUID) -> Optional[CredentialExecutor]:
        """Return the first executor that reports ``can_execute(resource_id)``.

        If no executor supports the resource, ``None`` is returned – callers
        should treat this as a fatal error (fail‑closed).
        """
        for exe in self._executors:
            if exe.can_execute(resource_id):
                return exe
        return None
