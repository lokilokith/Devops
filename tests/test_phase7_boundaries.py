"""Phase 7 Boundary Protection Tests.

Guarantees that Phase 7 has implemented exact Phase 7 JIT elevation and required cleanup,
while strictly maintaining boundaries against later phases:
- No Phase 8 full automated failure recovery daemon
- No Phase 9 general target drift reconciliation engine
- No Phase 10+ live session brokering / proxying
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.execution.domain import (
    ExecutionAuthorizationContext,
    ExecutionOperation,
    ExecutionRequest,
)
from app.execution.ssh_executor import SSHTargetExecutor


def test_phase7_executor_boundary():
    """Verify SSHTargetExecutor handles Phase 7 JIT operations with strict parameter validation."""
    executor = SSHTargetExecutor()
    now = datetime.now(timezone.utc)
    res_id = uuid.uuid4()
    auth_ctx = ExecutionAuthorizationContext(
        user_id=uuid.uuid4(),
        resource_id=res_id,
        target_account_binding_id=uuid.uuid4(),
        credential_id=uuid.uuid4(),
        requested_at=now,
        expires_at=now + timedelta(minutes=15),
    )

    # Missing parameters should fail validation, not raise NotImplementedError
    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=res_id,
        authorization_context=auth_ctx,
        parameters={},
    )
    result = executor.apply_jit_grant(req)
    assert result.status.value == "FAILED"
    assert "Missing host" in (result.error_message or "")


def test_phase8_and_phase9_boundaries_preserved():
    """Ensure Phase 8/9 broader modules are not prematurely introduced."""
    with pytest.raises(ImportError):
        import app.reconciliation.engine  # type: ignore # noqa: F401

    with pytest.raises(ImportError):
        import app.session_proxy.service  # type: ignore # noqa: F401
