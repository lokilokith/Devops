import pytest
from flask import Flask, jsonify
from werkzeug.exceptions import (
    BadRequest,
    Conflict,
    Forbidden,
    NotFound,
    Unauthorized,
    UnprocessableEntity,
)

from app.api.errors import errors_bp
from app.auth.service import AuthService
from app.extensions import db
from app.identity.models import User, UserStatus
from app.identity.repository import IdentityRepository


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    flask_app.config["JWT_SECRET_KEY"] = (
        "this-is-a-very-long-test-secret-key-that-is-at-least-32-bytes"
    )

    flask_app.register_blueprint(errors_bp)

    @flask_app.route("/error/400")
    def e400():
        raise BadRequest("Custom 400")

    @flask_app.route("/error/401")
    def e401():
        raise Unauthorized("Custom 401")

    @flask_app.route("/error/403")
    def e403():
        raise Forbidden("Custom 403")

    @flask_app.route("/error/404")
    def e404():
        raise NotFound("Custom 404")

    @flask_app.route("/error/409")
    def e409():
        raise Conflict("Custom 409")

    @flask_app.route("/error/422")
    def e422():
        raise UnprocessableEntity("Custom 422")

    @flask_app.route("/error/500")
    def e500():
        raise Exception("Unhandled exception")

    db.init_app(flask_app)
    with flask_app.app_context():
        import app.identity.models
        import app.permissions.models
        import app.resources.models
        import app.role_permissions.models
        import app.roles.models

        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    yield db.session
    db.session.rollback()
    db.session.remove()
