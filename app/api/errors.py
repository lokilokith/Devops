"""Global Error Handlers."""

from flask import Blueprint
from werkzeug.exceptions import HTTPException

from app.api.responses import error_response

errors_bp = Blueprint("errors", __name__)


@errors_bp.app_errorhandler(400)
def handle_400(error):
    return error_response(
        message=(
            str(error.description) if hasattr(error, "description") else "Bad Request"
        ),
        status_code=400,
    )


@errors_bp.app_errorhandler(401)
def handle_401(error):
    return error_response(
        message=(
            str(error.description) if hasattr(error, "description") else "Unauthorized"
        ),
        status_code=401,
    )


@errors_bp.app_errorhandler(403)
def handle_403(error):
    return error_response(
        message=(
            str(error.description) if hasattr(error, "description") else "Forbidden"
        ),
        status_code=403,
    )


@errors_bp.app_errorhandler(404)
def handle_404(error):
    return error_response(
        message=(
            str(error.description) if hasattr(error, "description") else "Not Found"
        ),
        status_code=404,
    )


@errors_bp.app_errorhandler(409)
def handle_409(error):
    return error_response(
        message=str(error.description) if hasattr(error, "description") else "Conflict",
        status_code=409,
    )


@errors_bp.app_errorhandler(422)
def handle_422(error):
    return error_response(
        message=(
            str(error.description)
            if hasattr(error, "description")
            else "Unprocessable Entity"
        ),
        status_code=422,
    )


@errors_bp.app_errorhandler(500)
def handle_500(error):
    return error_response(message="Internal Server Error", status_code=500)


@errors_bp.app_errorhandler(Exception)
def handle_exception(error):
    if isinstance(error, HTTPException):
        return error_response(message=error.description, status_code=error.code)
    return error_response(message="Internal Server Error", status_code=500)
