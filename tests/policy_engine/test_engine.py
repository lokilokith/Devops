import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock

import pytest

from app.access_requests.models import AccessRequest, AccessRequestStatus
from app.authorization.service import AuthorizationService
from app.policy_engine.decisions import PolicyDecision
from app.policy_engine.engine import PolicyEngine
from app.resources.models import ResourceAccessPolicy


@pytest.fixture
def mock_session():
    return Mock()


@pytest.fixture
def mock_authz():
    return Mock(spec=AuthorizationService)


@pytest.fixture
def engine(mock_session, mock_authz):
    return PolicyEngine(mock_session, mock_authz)


def test_evaluate_retrieval_no_roles(engine, mock_authz):
    mock_authz.get_user_roles.return_value = []
    
    decision = engine.evaluate_vault_retrieval(uuid.uuid4(), uuid.uuid4())
    assert decision == PolicyDecision.DENY


def test_evaluate_retrieval_no_policy_no_request(engine, mock_session, mock_authz):
    role_mock = Mock()
    role_mock.id = uuid.uuid4()
    mock_authz.get_user_roles.return_value = [role_mock]
    
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    
    decision = engine.evaluate_vault_retrieval(uuid.uuid4(), uuid.uuid4())
    assert decision == PolicyDecision.DENY


def test_evaluate_retrieval_policy_allows_no_approval(engine, mock_session, mock_authz):
    role_mock = Mock()
    role_mock.id = uuid.uuid4()
    mock_authz.get_user_roles.return_value = [role_mock]
    
    policy_mock = Mock(spec=ResourceAccessPolicy)
    policy_mock.approval_required = False
    
    mock_session.execute.return_value.scalars.return_value.all.return_value = [policy_mock]
    
    decision = engine.evaluate_vault_retrieval(uuid.uuid4(), uuid.uuid4())
    assert decision == PolicyDecision.ALLOW


def test_evaluate_retrieval_policy_requires_approval_no_request(engine, mock_session, mock_authz):
    role_mock = Mock()
    role_mock.id = uuid.uuid4()
    mock_authz.get_user_roles.return_value = [role_mock]
    
    policy_mock = Mock(spec=ResourceAccessPolicy)
    policy_mock.approval_required = True
    
    mock_session.execute.side_effect = [
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[policy_mock])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    ]
    
    decision = engine.evaluate_vault_retrieval(uuid.uuid4(), uuid.uuid4())
    assert decision == PolicyDecision.REQUIRE_APPROVAL


def test_evaluate_retrieval_policy_requires_approval_has_valid_request(engine, mock_session, mock_authz):
    role_mock = Mock()
    role_mock.id = uuid.uuid4()
    mock_authz.get_user_roles.return_value = [role_mock]
    
    policy_mock = Mock(spec=ResourceAccessPolicy)
    policy_mock.approval_required = True
    
    request_mock = Mock(spec=AccessRequest)
    request_mock.requested_start = datetime.now(timezone.utc) - timedelta(hours=1)
    request_mock.requested_end = datetime.now(timezone.utc) + timedelta(hours=1)
    
    mock_session.execute.side_effect = [
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[policy_mock])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[request_mock]))))
    ]
    
    decision = engine.evaluate_vault_retrieval(uuid.uuid4(), uuid.uuid4())
    assert decision == PolicyDecision.ALLOW
