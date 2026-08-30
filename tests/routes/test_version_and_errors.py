from flask import Flask, abort

from app.routes.version_routes import VersionResource
from app.utils.errors import register_error_handlers


def test_version_resource_get(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "test-commit-123")
    monkeypatch.setenv("BUILD_DATE", "2026-08-30")

    app = Flask(__name__)
    app.config["RESTX_MASK_HEADER"] = "X-Fields"
    app.config["RESTX_MASK_SWAGGER"] = False
    with app.test_request_context():
        resource = VersionResource()
        res = resource.get()

        assert "version" in res
        assert res["git_commit"] == "test-commit-123"
        assert res["build_date"] == "2026-08-30"


def test_global_error_handlers():
    app = Flask(__name__)
    register_error_handlers(app)

    @app.route("/bad-request")
    def trigger_bad_request():
        abort(400, description="Custom Bad Request")

    @app.route("/not-found")
    def trigger_not_found():
        abort(404, description="Custom Not Found")

    @app.route("/method-not-allowed", methods=["POST"])
    def trigger_method():
        return "ok"

    @app.route("/server-error")
    def trigger_server_error():
        abort(500, description="Custom 500")

    @app.route("/exception")
    def trigger_exception():
        raise RuntimeError("Crash unexpected")

    client = app.test_client()

    # 400
    r400 = client.get("/bad-request")
    assert r400.status_code == 400
    assert r400.json["success"] is False
    assert "Custom Bad Request" in r400.json["errors"]

    # 404
    r404 = client.get("/not-found")
    assert r404.status_code == 404
    assert r404.json["success"] is False

    # 405
    r405 = client.get("/method-not-allowed")
    assert r405.status_code == 405
    assert r405.json["success"] is False

    # 500
    r500 = client.get("/server-error")
    assert r500.status_code == 500
    assert r500.json["success"] is False

    # Exception
    rexc = client.get("/exception")
    assert rexc.status_code == 500
    assert rexc.json["success"] is False
