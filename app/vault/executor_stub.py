"""Stub Implementation of Credential Executor for Testing.

Deterministic test-double used by rotation workers and execution testing.
Inherits from StubTargetExecutor to provide full 6-method canonical TargetExecutor
support while preserving backwards compatibility for legacy execute() callers.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple, Union
from uuid import UUID

from app.execution.domain import ExecutionOperation
from app.execution.executor import StubTargetExecutor


class StubCredentialExecutor(StubTargetExecutor):
    """Deterministic stub executor supporting both canonical TargetExecutor and legacy CredentialExecutor."""

    def __init__(
        self,
        behaviour_map: Optional[
            Dict[Union[UUID, Tuple[UUID, ExecutionOperation]], str]
        ] = None,
    ) -> None:
        super().__init__(behaviour_map=behaviour_map)

    def execute(self, resource_id: UUID, current_secret: bytes) -> Dict[str, Any]:
        """Execute rotation for resource_id in legacy dictionary format."""
        mode = self._behaviour.get(resource_id, "success")
        if mode == "success":
            fake_blob = f"{resource_id}-{uuid.uuid4()}".encode()
            return {
                "new_secret_version": fake_blob,
                "metadata": {"generated_by": "stub"},
                "error": "",
            }
        if mode == "retry":
            raise RuntimeError("Transient error – retryable")
        if mode == "terminal":
            raise RuntimeError("Permanent error – terminal")
        raise RuntimeError(f"Execution failed with mode {mode}")
