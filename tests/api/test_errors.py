import pytest


def test_error_400(client):
    res = client.get("/error/400")
    assert res.status_code == 400
    assert res.json["success"] is False
    assert res.json["message"] == "Custom 400"


def test_error_401(client):
    res = client.get("/error/401")
    assert res.status_code == 401
    assert res.json["success"] is False
    assert res.json["message"] == "Custom 401"


def test_error_403(client):
    res = client.get("/error/403")
    assert res.status_code == 403
    assert res.json["success"] is False
    assert res.json["message"] == "Custom 403"


def test_error_404(client):
    res = client.get("/error/404")
    assert res.status_code == 404
    assert res.json["success"] is False
    assert res.json["message"] == "Custom 404"


def test_error_409(client):
    res = client.get("/error/409")
    assert res.status_code == 409
    assert res.json["success"] is False
    assert res.json["message"] == "Custom 409"


def test_error_422(client):
    res = client.get("/error/422")
    assert res.status_code == 422
    assert res.json["success"] is False
    assert res.json["message"] == "Custom 422"


def test_error_500(client):
    res = client.get("/error/500")
    assert res.status_code == 500
    assert res.json["success"] is False
    assert res.json["message"] == "Internal Server Error"


def test_error_unhandled_http_exception(app, client):
    from werkzeug.exceptions import ImATeapot

    @app.route("/error/418")
    def e418():
        raise ImATeapot("Short and stout")

    res = client.get("/error/418")
    assert res.status_code == 418
    assert res.json["success"] is False
    assert res.json["message"] == "Short and stout"
