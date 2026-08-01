"""Platform extension entrypoints."""

from app.extensions import db, migrate, limiter

__all__ = ["db", "migrate", "limiter"]
