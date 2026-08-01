import pytest
from app.api.responses import success_response
from app.api.errors import errors_bp
from flask import Flask
from werkzeug.exceptions import InternalServerError


def test_success_response():
    resp, code = success_response(data={"foo": "bar"}, message="Yay")
    assert code == 200
    assert resp["success"] is True
    assert resp["data"] == {"foo": "bar"}
    assert resp["message"] == "Yay"


def test_handle_500():
    app = Flask(__name__)
    app.register_blueprint(errors_bp)

    @app.route("/error/500")
    def e500():
        raise InternalServerError("Custom 500")

    client = app.test_client()
    res = client.get("/error/500")
    assert res.status_code == 500
    assert res.json["message"] == "Internal Server Error"
