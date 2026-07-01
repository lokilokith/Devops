"""OpsForge Threat Repository.

Encapsulates data access and persistence operations for the Threat model.
"""

from app.models.threat import Threat
from app.extensions import db
from sqlalchemy import or_


class ThreatRepository:
    """Repository implementation for SQLAlchemy-based Threat model operations."""

    @staticmethod
    def create(threat: Threat) -> Threat:
        """Adds a new threat intelligence record to the database session context."""
        db.session.add(threat)
        return threat

    @staticmethod
    def find_by_id(threat_id: int) -> Threat | None:
        """Fetches a threat intelligence record by its unique ID."""
        # Using Session.get() as recommended by SQLAlchemy 2.0
        return db.session.get(Threat, threat_id)

    @staticmethod
    def find_all() -> list[Threat]:
        """Fetches all threat intelligence records from the database."""
        return Threat.query.all()

    @staticmethod
    def find_by_status(status: str) -> list[Threat]:
        """Queries threat records matching a specific status."""
        return Threat.query.filter(Threat.status == status).all()

    @staticmethod
    def find_by_indicator_type(indicator_type: str) -> list[Threat]:
        """Queries threat records matching a specific indicator type."""
        return Threat.query.filter(Threat.indicator_type == indicator_type).all()

    @staticmethod
    def search(query_str: str) -> list[Threat]:
        """Performs a partial match search on indicator or source fields."""
        if not query_str:
            return []
        return Threat.query.filter(
            or_(
                Threat.indicator.ilike(f"%{query_str}%"),
                Threat.source.ilike(f"%{query_str}%"),
            )
        ).all()

    @staticmethod
    def update(threat: Threat) -> Threat:
        """Registers updated threat state in the database session context."""
        db.session.add(threat)
        return threat

    @staticmethod
    def delete(threat: Threat) -> None:
        """Deletes a threat record from the database session context."""
        db.session.delete(threat)

    @staticmethod
    def count() -> int:
        """Returns the total number of threat intelligence records."""
        return Threat.query.count()

    @staticmethod
    def paginate(filters: dict, page: int, limit: int, sort: str, order: str):
        """Queries threats with filtering, sorting, and windowed offset pagination."""
        query = Threat.query

        # Apply optional filters
        if filters.get("status"):
            query = query.filter(Threat.status == filters["status"])
        if filters.get("indicator_type"):
            query = query.filter(Threat.indicator_type == filters["indicator_type"])

        # Determine column to sort by
        sort_col = getattr(Threat, sort, Threat.created_at)
        if order.lower() == "desc":
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col.asc())

        # Perform windowed pagination
        return query.paginate(page=page, per_page=limit, error_out=False)
