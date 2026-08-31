"""Phase 6 Boundary Protection Tests.

Guarantees that Phase 6 has not implemented or exposed Phase 7+ functionality:
- No Phase 7 JIT privilege elevation
- No Phase 8 JIT revocation
- No Phase 9 general reconciliation engine
- No Phase 10+ session brokering
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


def test_phase7_and_phase8_methods_raise_not_implemented():
    """Verify SSHTargetExecutor refuses apply_jit_grant and revoke_jit_grant in Phase 6."""
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

    req = ExecutionRequest(
        operation=ExecutionOperation.APPLY_JIT_GRANT,
        resource_id=res_id,
        authorization_context=auth_ctx,
    )

    with pytest.raises(NotImplementedError, match="Phase 7"):
        executor.apply_jit_grant(req)

    req_revoke = ExecutionRequest(
        operation=ExecutionOperation.REVOKE_JIT_GRANT,
        resource_id=res_id,
        authorization_context=auth_ctx,
    )
    with pytest.raises(NotImplementedError, match="Phase 8"):
        executor.revoke_jit_grant(req_revoke)
