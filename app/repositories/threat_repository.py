"""OpsForge Threat Repository.

Encapsulates data access and persistence operations for the Threat model.
"""

from app.models.threat import Threat
from app.extensions import db
from sqlalchemy import or_
from app.utils.exceptions import ValidationException
from datetime import datetime


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
        return db.session.get(Threat, threat_id)

    @staticmethod
    def find_all() -> list[Threat]:
        """Fetches all threat intelligence records from the database using SQLAlchemy 2.0 select."""
        stmt = db.select(Threat)
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def find_by_status(status: str) -> list[Threat]:
        """Queries threat records matching a specific status using SQLAlchemy 2.0 select."""
        stmt = db.select(Threat).filter(Threat.status == status)
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def find_by_indicator_type(indicator_type: str) -> list[Threat]:
        """Queries threat records matching a specific indicator type using SQLAlchemy 2.0 select."""
        stmt = db.select(Threat).filter(Threat.indicator_type == indicator_type)
        return list(db.session.execute(stmt).scalars().all())

    @staticmethod
    def search(query_str: str) -> list[Threat]:
        """Performs a partial match search on indicator or source fields using SQLAlchemy 2.0 select."""
        if not query_str:
            return []
        stmt = db.select(Threat).filter(
            or_(
                Threat.indicator.ilike(f"%{query_str}%"),
                Threat.source.ilike(f"%{query_str}%"),
            )
        )
        return list(db.session.execute(stmt).scalars().all())

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
        """Returns the total number of threat intelligence records using SQLAlchemy 2.0 scalar count query."""
        stmt = db.select(db.func.count(Threat.id))
        return db.session.scalar(stmt) or 0

    ALLOWED_SORT_FIELDS = {
        "created_at": Threat.created_at,
        "updated_at": Threat.updated_at,
        "confidence": Threat.confidence,
        "indicator": Threat.indicator,
        "threat_level": Threat.threat_level,
    }

    @classmethod
    def paginate(cls, filters: dict, page: int, limit: int, sort: str, order: str):
        """Queries threats with filtering, sorting, and windowed offset pagination using db.paginate."""
        stmt = db.select(Threat)

        # Apply optional filters
        if filters.get("status"):
            stmt = stmt.filter(Threat.status == filters["status"])
        if filters.get("indicator_type"):
            stmt = stmt.filter(Threat.indicator_type == filters["indicator_type"])

        # Determine column to sort by using whitelist
        if sort not in cls.ALLOWED_SORT_FIELDS:
            raise ValidationException(
                f"Invalid sort field '{sort}'. Allowed fields are: {', '.join(cls.ALLOWED_SORT_FIELDS.keys())}."
            )

        sort_col = cls.ALLOWED_SORT_FIELDS[sort]
        if order.lower() == "desc":
            stmt = stmt.order_by(sort_col.desc())
        else:
            stmt = stmt.order_by(sort_col.asc())

        # Perform windowed pagination using Flask-SQLAlchemy 3.x db.paginate
        return db.paginate(stmt, page=page, per_page=limit, error_out=False)

    @staticmethod
    def count_by_status(status: str) -> int:
        """Returns the total count of threat indicators matching a status."""
        stmt = db.select(db.func.count(Threat.id)).filter(Threat.status == status)
        return db.session.scalar(stmt) or 0

    @staticmethod
    def count_by_level(threat_level: str) -> int:
        """Returns the total count of threat indicators matching a threat level."""
        stmt = db.select(db.func.count(Threat.id)).filter(
            Threat.threat_level == threat_level
        )
        return db.session.scalar(stmt) or 0

    @staticmethod
    def count_by_indicator_type(indicator_type: str) -> int:
        """Returns the total count of threat indicators matching an indicator type."""
        stmt = db.select(db.func.count(Threat.id)).filter(
            Threat.indicator_type == indicator_type
        )
        return db.session.scalar(stmt) or 0

    @staticmethod
    def latest_updated() -> datetime | None:
        """Returns the maximum updated_at timestamp across all indicators."""
        stmt = db.select(db.func.max(Threat.updated_at))
        return db.session.scalar(stmt)
