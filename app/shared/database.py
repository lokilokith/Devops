"""Shared database entrypoints."""

from app.extensions import db, migrate

__all__ = ["db", "migrate"]
