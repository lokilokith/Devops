"""OpsForge Production Hardening Tests.

Verifies Request ID headers, request logging, invalid sorting rejection, configuration validation, CORS headers, and WSGI entrypoint exports.
"""

import os
import pytest
from unittest.mock import patch
from app.utils.exceptions import ConfigurationException
from app.config import get_config


def test_request_id_header_and_logging(client, caplog):
    """Verifies that X-Request-ID is generated and returned, and request logging includes it."""
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


def test_invalid_sort_field_rejection(client):
    """Verifies that an invalid sort field in list query results in 400 Bad Request."""
    res = client.get("/threats?sort=malicious_field")
    assert res.status_code == 400
    data = res.get_json()
    assert data["success"] is False
    assert "Invalid sort field" in data["message"]


def test_cors_headers_development(client):
    """Verifies CORS headers allow localhost access in development config."""
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


def test_wsgi_entrypoint_imports():
    """Verifies that wsgi.py is importable and exposes the application instance."""
    from wsgi import app as wsgi_app

    assert wsgi_app is not None
    assert wsgi_app.name == "app"


def test_configuration_validation_errors():
    """Verifies that configuration loading validates APP_ENV, SECRET_KEY, and DATABASE_URL."""
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
    with patch.dict(os.environ, {"APP_ENV": "production", "SECRET_KEY": "supersecret"}):
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        with pytest.raises(ConfigurationException) as exc:
            get_config()
        assert "DATABASE_URL environment variable is missing" in str(exc.value)


def test_extra_routes_error_coverage(client):
    """Triggers 405 Method Not Allowed and unhandled 500 exceptions for full controller coverage."""
    # 1. 405 Method Not Allowed (POST /health)
    res_405 = client.post("/health")
    assert res_405.status_code == 405
    data_405 = res_405.get_json()
    assert data_405["success"] is False
    assert "Method Not Allowed" in data_405["message"]

    # 2. 500 Unhandled raw Python exceptions
    with patch(
        "app.services.threat_service.ThreatService.get_threat",
        side_effect=RuntimeError("Test crash"),
    ):
        res_500 = client.get("/threats/1")
        assert res_500.status_code == 500
        data_500 = res_500.get_json()
        assert data_500["success"] is False
        assert "unexpected server error" in data_500["message"].lower()


def test_service_failures_coverage(app, db_session):
    """Triggers database operation exceptions for update, delete, and status changes in ThreatService."""
    from app.services.threat_service import ThreatService
    from app.utils.exceptions import DatabaseOperationException

    # Create a threat
    threat = ThreatService.create_threat(
        {
            "indicator": "1.2.3.4",
            "indicator_type": "ip",
            "threat_level": "low",
            "confidence": 50,
            "source": "test",
        }
    )

    # 1. database error on update
    with patch("app.extensions.db.session.commit", side_effect=Exception("DB Error")):
        with pytest.raises(DatabaseOperationException):
            ThreatService.update_threat(threat.id, {"indicator": "2.3.4.5"})

    # 2. database error on status change
    with patch("app.extensions.db.session.commit", side_effect=Exception("DB Error")):
        with pytest.raises(DatabaseOperationException):
            ThreatService.change_status(threat.id, "Investigating", "analyst_bob")

    # 3. database error on delete
    with patch("app.extensions.db.session.commit", side_effect=Exception("DB Error")):
        with pytest.raises(DatabaseOperationException):
            ThreatService.delete_threat(threat.id)
