"""Standardized API Responses."""


def success_response(data=None, message="Success", meta=None, status_code=200):
    response = {
        "success": True,
        "message": message,
        "data": data or {},
        "meta": meta or {},
    }
    return response, status_code


def error_response(message="An error occurred", data=None, status_code=400):
    response = {"success": False, "message": message, "data": data or {}, "meta": {}}
    return response, status_code
