"""OpsForge Middleware.

Implements request logging, Request ID generation, and header injection.
"""

import time
import uuid
import logging
import os
from flask import Flask, request, g

logger = logging.getLogger("opsforge")

# Read application version from root VERSION file once
version = "0.1.0"
try:
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    version_path = os.path.join(root_dir, "VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as f:
            version = f.read().strip()
except Exception:
    pass


def register_middleware(app: Flask) -> None:
    """Registers request logging and response header middleware on the Flask app."""

    @app.before_request
    def before_request_func():
        # Retrieve or generate Request ID
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = req_id
        g.start_time = time.time()

    @app.after_request
    def after_request_func(response):
        # Calculate response duration
        duration_ms = 0.0
        if hasattr(g, "start_time"):
            duration_ms = (time.time() - g.start_time) * 1000

        req_id = getattr(g, "request_id", "unknown-id")

        # Log HTTP request details
        logger.info(
            f"[{req_id}] {request.remote_addr} - \"{request.method} {request.path} {request.environ.get('SERVER_PROTOCOL')}\" "
            f"{response.status_code} ({duration_ms:.2f}ms)"
        )

        # Attach custom headers
        response.headers["X-Request-ID"] = req_id
        response.headers["X-OpsForge-Version"] = version

        return response
