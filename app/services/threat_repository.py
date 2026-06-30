"""OpsForge Threat Repository.

Handles database persistence operations for the Threat model.
"""

from app.models.threat import Threat
from app.extensions import db


class ThreatRepository:
    """Repository class encapsulating database access for Threat records."""

    @staticmethod
    def create(threat: Threat) -> Threat:
        """Adds a threat record to the database session context."""
        db.session.add(threat)
        return threat

    @staticmethod
    def find_by_id(threat_id: int) -> Threat:
        """Fetches a single threat record by its unique identifier."""
        return Threat.query.get(threat_id)

    @staticmethod
    def find_by_status(status: str) -> list[Threat]:
        """Fetches threat records filtering by status lifecycle state."""
        return Threat.query.filter(Threat.status == status).all()

    @staticmethod
    def find_by_indicator(indicator: str) -> list[Threat]:
        """Fetches threat records matching a specific indicator value."""
        return Threat.query.filter(Threat.indicator == indicator).all()

    @staticmethod
    def update(threat: Threat) -> Threat:
        """Saves/registers updated threat model state in the session."""
        db.session.add(threat)
        return threat

    @staticmethod
    def delete(threat: Threat) -> None:
        """Deletes a threat record from the database session."""
        db.session.delete(threat)

    @staticmethod
    def paginate(filters: dict, page: int, limit: int, sort: str, order: str):
        """Query threat records applying optional filters, sorting, and pagination."""
        query = Threat.query

        # Apply filtering
        if filters.get("status"):
            query = query.filter(Threat.status == filters["status"])
        if filters.get("indicator_type"):
            query = query.filter(Threat.indicator_type == filters["indicator_type"])

        # Determine sorting field
        sort_col = getattr(Threat, sort, Threat.created_at)
        if order.lower() == "desc":
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col.asc())

        # Perform pagination sweep
        return query.paginate(page=page, per_page=limit, error_out=False)
