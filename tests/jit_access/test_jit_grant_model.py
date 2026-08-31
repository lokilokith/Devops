"""Domain model tests for JITAccessGrant in Phase 7."""

import uuid
from datetime import datetime, timedelta, timezone

from app.jit_access.models import JITAccessGrant, JITGrantStatus


def test_jit_grant_status_enum_values():
    """Verify all required Phase 7 lifecycle states exist."""
    assert JITGrantStatus.PENDING.value == "pending"
    assert JITGrantStatus.ACTIVE.value == "active"
    assert JITGrantStatus.EXPIRED.value == "expired"
    assert JITGrantStatus.REVOKED.value == "revoked"
    assert JITGrantStatus.DENIED.value == "denied"
    assert JITGrantStatus.FAILED.value == "failed"
    assert JITGrantStatus.SECURITY_UNCERTAIN.value == "security_uncertain"


def test_jit_grant_model_initialization():
    """Verify model fields, defaults, and optimistic locking row_version."""
    user_id = uuid.uuid4()
    role_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    ar_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=30)

    grant = JITAccessGrant(
        user_id=user_id,
        role_id=role_id,
        resource_id=resource_id,
        target_account_binding_id=binding_id,
        command_set_id="system_health_check",
        approval_request_id=ar_id,
        status=JITGrantStatus.PENDING,
        expires_at=exp,
        row_version=1,
    )

    assert grant.user_id == user_id
    assert grant.target_account_binding_id == binding_id
    assert grant.command_set_id == "system_health_check"
    assert grant.status == JITGrantStatus.PENDING
    assert grant.expires_at == exp
    assert grant.row_version == 1
    assert grant.observed_overrun_ms is None
