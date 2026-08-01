"""OpsForge Production Hardening Tests.

Verifies Request ID headers, request logging, configuration
validation, CORS headers, WSGI entrypoint exports, and global
error handler coverage.
"""

import os
from unittest.mock import patch

import pytest

from app.config import get_config
from app.utils.exceptions import ConfigurationException


def test_request_id_header_and_logging(client, caplog):
    """Verify X-Request-ID generation, return, and log inclusion."""
    import logging

    logger = logging.getLogger("opsforge")
    logger.propagate = True
    try:
        with caplog.at_level(logging.INFO, logger="opsforge"):
            res = client.get("/health")
            assert res.status_code == 200

            # Check custom headers are attached
            assert "X-Request-ID" in res.headers
            assert "X-OpsForge-Version" in res.headers
            req_id = res.headers["X-Request-ID"]
            assert len(req_id) > 0

            # Check that the logs contain the request ID
            log_records = [rec.message for rec in caplog.records]
            assert any(req_id in msg for msg in log_records)
            assert any("GET /health" in msg for msg in log_records)
    finally:
        logger.propagate = False


def test_cors_headers_development(client):
    """Verify CORS headers allow localhost access in development."""
    res = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert res.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


def test_wsgi_entrypoint_imports():
    """Verify wsgi.py is importable and exposes the app instance."""
    from wsgi import app as wsgi_app

    assert wsgi_app is not None
    assert wsgi_app.name == "app"


def test_configuration_validation_errors():
    """Verify config validates APP_ENV, SECRET_KEY, DATABASE_URL."""
    # 1. Missing APP_ENV
    with patch.dict(os.environ, {}):
        if "APP_ENV" in os.environ:
            del os.environ["APP_ENV"]
        with pytest.raises(ConfigurationException) as exc:
            get_config()
        assert "APP_ENV environment variable is missing" in str(exc.value)

    # 2. Invalid APP_ENV value
    with patch.dict(os.environ, {"APP_ENV": "unsupported_env"}):
        with pytest.raises(ConfigurationException) as exc:
            get_config()
        assert "Unsupported APP_ENV" in str(exc.value)

    # 3. Production missing SECRET_KEY
    with patch.dict(
        os.environ,
        {"APP_ENV": "production", "DATABASE_URL": "postgresql://local"},
    ):
        if "SECRET_KEY" in os.environ:
            del os.environ["SECRET_KEY"]
        with pytest.raises(ConfigurationException) as exc:
            get_config()
        assert "SECRET_KEY environment variable is missing" in str(exc.value)

    # 4. Production missing DATABASE_URL
    with patch.dict(
        os.environ,
        {"APP_ENV": "production", "SECRET_KEY": "supersecret"},
    ):
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        with pytest.raises(ConfigurationException) as exc:
            get_config()
        assert "DATABASE_URL environment variable is missing" in str(exc.value)


def test_error_handler_405(client):
    """Verify 405 Method Not Allowed returns JSON error format."""
    res_405 = client.post("/health")
    assert res_405.status_code == 405
    data_405 = res_405.get_json()
    assert data_405["success"] is False
    assert "Method Not Allowed" in data_405["message"]


def test_error_handler_404(client):
    """Verify 404 Not Found returns JSON error format."""
    res_404 = client.get("/nonexistent-path-at-root")
    assert res_404.status_code == 404
    data_404 = res_404.get_json()
    assert data_404["success"] is False
    assert len(data_404["errors"]) > 0


def test_health_endpoint_response_structure(client):
    """Verify health endpoint returns complete response structure."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()

    assert data["success"] is True
    assert "status check" in data["message"].lower()
    assert data["data"]["application"] == "healthy"
    assert data["data"]["database"] == "healthy"
    assert "version" in data["data"]
    assert "uptime" in data["data"]
