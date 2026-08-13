import pytest
from datetime import datetime, timezone, timedelta
import uuid
from unittest.mock import Mock, patch

from app.jit_access.models import JITAccessGrant, JITGrantStatus, JITAccessSession
from app.jit_access.service import JITAccessService, InvalidGrantStateError

def test_jit_session_creation():
    grant = JITAccessGrant(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        approval_request_id=uuid.uuid4(),
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    
    mock_repo = Mock()
    mock_repo.get_by_id.return_value = grant
    mock_vault_service = Mock()
    mock_secret = Mock()
    mock_secret.id = uuid.uuid4()
    mock_vault_service.create_secret.return_value = mock_secret
    
    # Mock db and extensions
    with patch("app.jit_access.service.db") as mock_db, patch("app.jit_access.events.jit_session_created") as mock_event:
        # Mock idempotency check returning None
        mock_db.session.execute.return_value.scalar_one_or_none.return_value = None
        
        service = JITAccessService(mock_repo, Mock(), Mock(), Mock(), Mock())
        system_actor = uuid.uuid4()
        
        session = service.create_session(grant.id, system_actor, mock_vault_service, b"dummy")
        
        assert session.access_request_id == grant.approval_request_id
        assert session.ephemeral_secret_id == mock_secret.id
        mock_vault_service.create_secret.assert_called_once_with(system_actor, grant.resource_id, b"dummy")
        mock_event.send.assert_called_once()
        mock_db.session.add.assert_called()

def test_jit_session_expiration_and_revocation_idempotency():
    session = JITAccessSession(
        access_request_id=uuid.uuid4(),
        ephemeral_secret_id=uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    
    # First expire
    changed = session.expire()
    assert changed is True
    assert session.expires_at <= datetime.now(timezone.utc)
    
    # Second expire (idempotent)
    changed = session.expire()
    assert changed is False
    
    # Revoke
    changed = session.revoke()
    assert changed is True
    assert session.revoked_at is not None
    
    # Second revoke (idempotent)
    changed = session.revoke()
    assert changed is False
    
    # Cannot expire after revoked
    with pytest.raises(ValueError, match="Cannot expire a revoked session"):
        session.expire()

def test_jit_service_expire_access():
    grant = JITAccessGrant(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        resource_id=uuid.uuid4(),
        approval_request_id=uuid.uuid4(),
        status=JITGrantStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    
    session = JITAccessSession(
        access_request_id=grant.approval_request_id,
        ephemeral_secret_id=uuid.uuid4(),
        expires_at=grant.expires_at,
    )
    
    mock_repo = Mock()
    mock_repo.get_by_id.return_value = grant
    mock_repo.update.return_value = grant
    
    with patch("app.jit_access.service.db") as mock_db, patch("app.jit_access.events.jit_session_expired") as mock_event:
        mock_db.session.execute.return_value.scalar_one_or_none.return_value = session
        
        service = JITAccessService(mock_repo, Mock(), Mock(), Mock(), Mock())
        service.expire_access(grant.id)
        
        assert grant.status == JITGrantStatus.EXPIRED
        assert session.expires_at <= datetime.now(timezone.utc)
        mock_event.send.assert_called_once()

    # Call again (idempotent)
    with patch("app.jit_access.service.db") as mock_db:
        service.expire_access(grant.id)
        # shouldn't raise exception, just returns grant
        assert grant.status == JITGrantStatus.EXPIRED

def test_jit_service_invalid_transitions():
    grant = JITAccessGrant(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status=JITGrantStatus.PENDING,
    )
    
    mock_repo = Mock()
    mock_repo.get_by_id.return_value = grant
    
    service = JITAccessService(mock_repo, Mock(), Mock(), Mock(), Mock())
    
    with pytest.raises(InvalidGrantStateError):
        service.expire_access(grant.id)
