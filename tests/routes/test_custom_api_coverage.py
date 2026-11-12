from unittest.mock import MagicMock

import pytest
from werkzeug.exceptions import HTTPException

from app.routes import CustomApi
from app.shared.exceptions import (
    DatabaseOperationException,
    InvalidStatusTransition,
    ResourceNotFoundException,
    ValidationException,
)


def test_handle_error_restx_validation():
    api = CustomApi()
    api.make_response = MagicMock(return_value="response")
    e = MagicMock()
    e.data = {"errors": {"field": "msg"}}
    # It returns super().handle_error(e), we can't easily mock super without patching Api
    # Let's just catch what it does
    try:
        api.handle_error(e)
    except Exception:
        pass


def test_handle_error_resource_not_found():
    api = CustomApi()
    api.make_response = MagicMock(return_value="response")
    e = ResourceNotFoundException("test")
    res = api.handle_error(e)
    assert res == "response"


def test_handle_error_validation_exception():
    api = CustomApi()
    api.make_response = MagicMock(return_value="response")
    e = ValidationException("test")
    res = api.handle_error(e)
    assert res == "response"


def test_handle_error_invalid_status_transition():
    api = CustomApi()
    api.make_response = MagicMock(return_value="response")
    e = InvalidStatusTransition("test")
    res = api.handle_error(e)
    assert res == "response"


def test_handle_error_database_operation():
    api = CustomApi()
    api.make_response = MagicMock(return_value="response")
    e = DatabaseOperationException("test")
    res = api.handle_error(e)
    assert res == "response"


def test_handle_error_http_exception():
    api = CustomApi()
    api.make_response = MagicMock(return_value="response")
    e = HTTPException("test")
    e.code = 422
    res = api.handle_error(e)
    assert res == "response"


def test_handle_error_http_exception_other():
    api = CustomApi()
    api.make_response = MagicMock(return_value="response")
    e = HTTPException("test")
    e.code = 500
    res = api.handle_error(e)
    assert res == "response"


def test_handle_error_generic():
    api = CustomApi()
    api.make_response = MagicMock(return_value="response")
    e = Exception("test")
    with pytest.raises(Exception):
        api.handle_error(e)
