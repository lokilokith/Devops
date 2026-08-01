"""Platform extension entrypoints."""

from app.extensions import db, limiter, migrate

__all__ = ["db", "migrate", "limiter"]
