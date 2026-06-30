"""OpsForge API Error Handlers.

Registers global error handlers on the Flask-RESTX Api object.
"""

from flask_restx import Api
from werkzeug.exceptions import BadRequest, NotFound, MethodNotAllowed
from app.utils.custom_exceptions import (
    ValidationException,
    ResourceNotFoundException,
    DatabaseException,
)


def register_error_handlers(api: Api) -> None:
    """Registers global error handlers to format failure responses uniformly."""

    @api.errorhandler(ValidationException)
    def handle_validation_exception(error: ValidationException):
        """Formats ValidationException as API Standard Failure."""
        return {"success": False, "message": error.message, "errors": error.errors}, 400

    @api.errorhandler(ResourceNotFoundException)
    def handle_not_found_exception(error: ResourceNotFoundException):
        """Formats ResourceNotFoundException as API Standard Failure."""
        return {
            "success": False,
            "message": error.message,
            "errors": [error.message],
        }, 404

    @api.errorhandler(DatabaseException)
    def handle_database_exception(error: DatabaseException):
        """Formats DatabaseException as API Standard Failure."""
        return {"success": False, "message": error.message, "errors": error.errors}, 500

    @api.errorhandler(BadRequest)
    def handle_bad_request(error: BadRequest):
        """Formats standard HTTP BadRequest as API Standard Failure."""
        return {
            "success": False,
            "message": "Bad Request",
            "errors": [
                error.description or "The server could not understand the request."
            ],
        }, 400

    @api.errorhandler(NotFound)
    def handle_not_found(error: NotFound):
        """Formats standard HTTP NotFound as API Standard Failure."""
        return {
            "success": False,
            "message": "Resource Not Found",
            "errors": [
                error.description or "The requested URL was not found on the server."
            ],
        }, 404

    @api.errorhandler(MethodNotAllowed)
    def handle_method_not_allowed(error: MethodNotAllowed):
        """Formats standard HTTP MethodNotAllowed as API Standard Failure."""
        return {
            "success": False,
            "message": "Method Not Allowed",
            "errors": [
                error.description or "The method is not allowed for the requested URL."
            ],
        }, 405

    @api.errorhandler(Exception)
    def handle_generic_exception(error: Exception):
        """Catch-all handler formatting raw exceptions as API Standard Failure."""
        return {
            "success": False,
            "message": "An unexpected server error occurred",
            "errors": [str(error)],
        }, 500
