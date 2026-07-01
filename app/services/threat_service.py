"""OpsForge Threat Service.

Orchestrates business workflows, validates data parameters, and manages database transactions.
"""

import logging
from datetime import datetime, timezone
from app.models.threat import Threat
from app.repositories.threat_repository import ThreatRepository
from app.extensions import db
from app.utils.exceptions import (
    ValidationException,
    ThreatNotFoundException,
    InvalidStatusTransition,
    DatabaseOperationException,
)
from app.utils.validators import validate_threat_data, validate_create_threat_data

logger = logging.getLogger("opsforge")


class ThreatService:
    """Service layer managing threat intelligence business workflows."""

    @staticmethod
    def create_threat(data: dict) -> Threat:
        """Validates payload and inserts a new threat indicator."""
        validate_create_threat_data(data)

        # Map input payload to model instance
        threat = Threat(
            indicator=data["indicator"],
            indicator_type=data["indicator_type"],
            threat_level=data["threat_level"],
            confidence=int(data["confidence"]),
            mitre_attack=data.get("mitre_attack"),
            source=data["source"],
            analyst_notes=data.get("analyst_notes"),
            assigned_analyst=data.get("assigned_analyst"),
            tags=data.get("tags", []),
            first_seen=data.get("first_seen"),
            last_seen=data.get("last_seen"),
        )

        try:
            ThreatRepository.create(threat)
            db.session.commit()
            return threat
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during threat creation: {str(e)}")
            raise DatabaseOperationException(
                f"Failed to create threat indicator: {str(e)}"
            )

    @staticmethod
    def get_threat(threat_id: int) -> Threat:
        """Fetches a threat by ID or raises ThreatNotFoundException."""
        threat = ThreatRepository.find_by_id(threat_id)
        if not threat:
            raise ThreatNotFoundException(f"Threat with ID {threat_id} does not exist.")
        return threat

    @staticmethod
    def list_threats(filters: dict, page: int, limit: int, sort: str, order: str):
        """Retrieves paginated threat indicators matching filtering criteria."""
        return ThreatRepository.paginate(filters, page, limit, sort, order)

    @staticmethod
    def update_threat(threat_id: int, data: dict) -> Threat:
        """Validates payload updates and writes changes to database."""
        threat = ThreatService.get_threat(threat_id)

        # Validate update parameters
        validate_threat_data(data)

        # Explicitly map update payload to model fields
        if "indicator" in data:
            threat.indicator = data["indicator"]
        if "indicator_type" in data:
            threat.indicator_type = data["indicator_type"]
        if "threat_level" in data:
            threat.threat_level = data["threat_level"]
        if "confidence" in data:
            threat.confidence = int(data["confidence"])
        if "mitre_attack" in data:
            threat.mitre_attack = data["mitre_attack"]
        if "source" in data:
            threat.source = data["source"]
        if "analyst_notes" in data:
            threat.analyst_notes = data["analyst_notes"]
        if "assigned_analyst" in data:
            threat.assigned_analyst = data["assigned_analyst"]
        if "tags" in data:
            threat.tags = data["tags"]
        if "first_seen" in data:
            threat.first_seen = data["first_seen"]
        if "last_seen" in data:
            threat.last_seen = data["last_seen"]

        try:
            ThreatRepository.update(threat)
            db.session.commit()
            return threat
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during threat update: {str(e)}")
            raise DatabaseOperationException(
                f"Failed to update threat {threat_id}: {str(e)}"
            )

    @staticmethod
    def delete_threat(threat_id: int) -> None:
        """Purges a threat indicator record."""
        threat = ThreatService.get_threat(threat_id)
        try:
            ThreatRepository.delete(threat)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during threat deletion: {str(e)}")
            raise DatabaseOperationException(
                f"Failed to delete threat {threat_id}: {str(e)}"
            )

    @staticmethod
    def change_status(threat_id: int, new_status: str, analyst_name: str) -> Threat:
        """Enforces workflow transition validations and updates status field."""
        threat = ThreatService.get_threat(threat_id)

        # Enforce Threat Status State Machine
        allowed_transitions = {
            "Open": ["Investigating"],
            "Investigating": ["Contained", "False Positive"],
            "Contained": ["Closed"],
            "False Positive": ["Closed"],
        }

        current_status = threat.status
        if current_status == new_status:
            return threat

        # Validate transition pathway
        valid_destinations = allowed_transitions.get(current_status, [])
        if new_status not in valid_destinations:
            raise InvalidStatusTransition(
                f"Illegal transition pathway: cannot change status from '{current_status}' to '{new_status}'."
            )

        # Apply update
        threat.status = new_status
        if analyst_name:
            threat.assigned_analyst = analyst_name

        try:
            ThreatRepository.update(threat)
            db.session.commit()
            return threat
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during status change: {str(e)}")
            raise DatabaseOperationException(
                f"Failed to update status for threat {threat_id}: {str(e)}"
            )

    @staticmethod
    def search_threats(query_str: str) -> list[Threat]:
        """Runs search queries against indicator keys."""
        return ThreatRepository.search(query_str)

    @staticmethod
    def get_statistics() -> dict:
        """Compiles global aggregation metrics from all indicators."""
        try:
            total_threats = ThreatRepository.count()

            critical = ThreatRepository.count_by_level("critical")
            high = ThreatRepository.count_by_level("high")
            medium = ThreatRepository.count_by_level("medium")
            low = ThreatRepository.count_by_level("low")

            open_count = ThreatRepository.count_by_status("Open")
            investigating = ThreatRepository.count_by_status("Investigating")
            contained = ThreatRepository.count_by_status("Contained")
            closed = ThreatRepository.count_by_status("Closed")
            false_positive = ThreatRepository.count_by_status("False Positive")

            # Count indicator types
            indicator_type_counts = {}
            from app.constants import INDICATOR_TYPES

            for ind_type in INDICATOR_TYPES:
                indicator_type_counts[ind_type] = (
                    ThreatRepository.count_by_indicator_type(ind_type)
                )

            # Get last updated timestamp
            last_updated_dt = ThreatRepository.latest_updated()
            last_updated_str = None
            if last_updated_dt:
                if last_updated_dt.tzinfo is None:
                    last_updated_dt = last_updated_dt.replace(tzinfo=timezone.utc)
                last_updated_str = last_updated_dt.isoformat()

            return {
                "total_threats": total_threats,
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": low,
                "open": open_count,
                "investigating": investigating,
                "contained": contained,
                "closed": closed,
                "false_positive": false_positive,
                "indicator_type_counts": indicator_type_counts,
                "last_updated": last_updated_str,
            }
        except Exception as e:
            logger.error(f"Database error during statistics compilation: {str(e)}")
            raise DatabaseOperationException(
                f"Failed to compile threat metrics: {str(e)}"
            )
