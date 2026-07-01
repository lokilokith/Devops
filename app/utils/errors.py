"""OpsForge Global JSON Error Handlers."""

from flask import Flask, jsonify
from werkzeug.exceptions import (
    BadRequest,
    NotFound,
    MethodNotAllowed,
    InternalServerError,
)


def register_error_handlers(app: Flask) -> None:
    """Registers global JSON error handlers on the Flask application."""

    @app.errorhandler(400)
    @app.errorhandler(BadRequest)
    def handle_bad_request(error):
        description = getattr(
            error, "description", "The server could not understand the request."
        )
        return (
            jsonify(
                {"success": False, "message": "Bad Request", "errors": [description]}
            ),
            400,
        )

    @app.errorhandler(404)
    @app.errorhandler(NotFound)
    def handle_not_found(error):
        description = getattr(
            error, "description", "The requested URL was not found on the server."
        )
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Resource Not Found",
                    "errors": [description],
                }
            ),
            404,
        )

    @app.errorhandler(405)
    @app.errorhandler(MethodNotAllowed)
    def handle_method_not_allowed(error):
        description = getattr(
            error, "description", "The method is not allowed for the requested URL."
        )
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Method Not Allowed",
                    "errors": [description],
                }
            ),
            405,
        )

    @app.errorhandler(500)
    @app.errorhandler(InternalServerError)
    def handle_internal_server_error(error):
        description = getattr(
            error, "description", "An unexpected system error occurred."
        )
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Internal Server Error",
                    "errors": [description],
                }
            ),
            500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "An unexpected server error occurred",
                    "errors": [str(error)],
                }
            ),
            500,
        )
