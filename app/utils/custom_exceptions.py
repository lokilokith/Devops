"""OpsForge Custom Exceptions.

Defines strongly typed exceptions to guarantee semantic handling across layers.
"""


class ValidationException(Exception):
    """Exception raised when input validation fails (HTTP 400)."""

    def __init__(self, message: str, errors: list = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


class ResourceNotFoundException(Exception):
    """Exception raised when a requested resource is not found (HTTP 404)."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ConfigurationException(Exception):
    """Exception raised when application bootstrap configurations are invalid or missing."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DatabaseException(Exception):
    """Exception raised for database-related persistence failures (HTTP 500)."""

    def __init__(self, message: str, errors: list = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]
