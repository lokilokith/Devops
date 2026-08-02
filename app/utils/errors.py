"""OpsForge Global JSON Error Handlers."""

from flask import Flask, jsonify


def register_error_handlers(app: Flask) -> None:
    """Registers global JSON error handlers on the Flask application."""

    @app.errorhandler(400)
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
    def handle_internal_server_error(error):
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)
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
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)
        app.logger.error(f"Unexpected Exception: {str(error)}", exc_info=True)
        return (
            jsonify(
                {
                    "success": False,
                    "message": "An unexpected server error occurred",
                    "errors": ["An internal error occurred."],
                }
            ),
            500,
        )
