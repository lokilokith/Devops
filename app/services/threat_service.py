"""OpsForge Threat Service.

Orchestrates business logic rules, validations, and transitions for Threat records.
"""

from datetime import datetime
from app.extensions import db
from app.models.threat import Threat
from app.services.threat_repository import ThreatRepository
from app.utils.custom_exceptions import (
    ResourceNotFoundException,
    ValidationException,
    DatabaseException,
)
from app.constants import THREAT_LEVELS, THREAT_STATUSES, INDICATOR_TYPES


class ThreatService:
    """Service layer class orchestrating business logic for Threat management."""

    @staticmethod
    def create_threat(data: dict) -> Threat:
        """Validates input, constructs and persists a new Threat intelligence record."""
        # Validation
        confidence = data.get("confidence")
        if confidence is None:
            raise ValidationException("Confidence is a required field")
        try:
            conf_val = int(confidence)
            if conf_val < 0 or conf_val > 100:
                raise ValidationException("Confidence must be between 0 and 100")
        except (TypeError, ValueError):
            raise ValidationException("Confidence must be an integer between 0 and 100")

        ind_type = data.get("indicator_type")
        if not ind_type or ind_type not in INDICATOR_TYPES:
            raise ValidationException(
                f"Invalid indicator_type. Must be one of: {INDICATOR_TYPES}"
            )

        level = data.get("threat_level")
        if not level or level not in THREAT_LEVELS:
            raise ValidationException(
                f"Invalid threat_level. Must be one of: {THREAT_LEVELS}"
            )

        status = data.get("status", "Open")
        if status not in THREAT_STATUSES:
            raise ValidationException(
                f"Invalid status. Must be one of: {THREAT_STATUSES}"
            )

        indicator = data.get("indicator")
        if not indicator:
            raise ValidationException("Indicator is a required field")

        source = data.get("source")
        if not source:
            raise ValidationException("Source is a required field")

        # Parse date strings to timezone-aware datetimes
        first_seen = data.get("first_seen")
        if first_seen:
            try:
                first_seen = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            except ValueError:
                raise ValidationException(
                    "first_seen must be a valid ISO format datetime"
                )

        last_seen = data.get("last_seen")
        if last_seen:
            try:
                last_seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            except ValueError:
                raise ValidationException(
                    "last_seen must be a valid ISO format datetime"
                )

        tags = data.get("tags")
        if tags is not None and not isinstance(tags, list):
            raise ValidationException("tags must be a JSON list of strings")

        threat = Threat(
            indicator=indicator,
            indicator_type=ind_type,
            threat_level=level,
            confidence=conf_val,
            mitre_attack=data.get("mitre_attack"),
            source=source,
            analyst_notes=data.get("analyst_notes"),
            assigned_analyst=data.get("assigned_analyst"),
            last_updated_by=data.get("assigned_analyst"),  # Initial audit marker
            status=status,
            tags=tags,
            first_seen=first_seen,
            last_seen=last_seen,
        )

        try:
            ThreatRepository.create(threat)
            db.session.commit()
            return threat
        except Exception as e:
            db.session.rollback()
            raise DatabaseException(f"Failed to create threat: {str(e)}")

    @staticmethod
    def get_threats(pagination_params: dict, filter_params: dict):
        """Orchestrates query parameter logic, sorting and pagination."""
        page = pagination_params.get("page", 1)
        limit = pagination_params.get("limit", 20)
        sort = pagination_params.get("sort", "created_at")
        order = pagination_params.get("order", "desc")

        # Validate sorting column
        if sort not in [
            "id",
            "indicator",
            "indicator_type",
            "threat_level",
            "confidence",
            "status",
            "created_at",
            "updated_at",
        ]:
            sort = "created_at"

        # Validate filters
        status = filter_params.get("status")
        if status and status not in THREAT_STATUSES:
            raise ValidationException(
                f"Invalid status filter. Must be one of: {THREAT_STATUSES}"
            )

        ind_type = filter_params.get("indicator_type")
        if ind_type and ind_type not in INDICATOR_TYPES:
            raise ValidationException(
                f"Invalid indicator_type filter. Must be one of: {INDICATOR_TYPES}"
            )

        filters = {"status": status, "indicator_type": ind_type}

        try:
            return ThreatRepository.paginate(filters, page, limit, sort, order)
        except Exception as e:
            raise DatabaseException(f"Failed to retrieve threats: {str(e)}")

    @staticmethod
    def get_threat_by_id(threat_id: int) -> Threat:
        """Fetches a single threat model, throwing ResourceNotFoundException if absent."""
        threat = ThreatRepository.find_by_id(threat_id)
        if not threat:
            raise ResourceNotFoundException(f"Threat with ID {threat_id} not found")
        return threat

    @staticmethod
    def update_threat(threat_id: int, data: dict) -> Threat:
        """Performs atomic resource updates and traces auditing data."""
        threat = ThreatService.get_threat_by_id(threat_id)

        # Validation
        confidence = data.get("confidence")
        if confidence is not None:
            try:
                conf_val = int(confidence)
                if conf_val < 0 or conf_val > 100:
                    raise ValidationException("Confidence must be between 0 and 100")
                threat.confidence = conf_val
            except (TypeError, ValueError):
                raise ValidationException(
                    "Confidence must be an integer between 0 and 100"
                )

        ind_type = data.get("indicator_type")
        if ind_type:
            if ind_type not in INDICATOR_TYPES:
                raise ValidationException(
                    f"Invalid indicator_type. Must be one of: {INDICATOR_TYPES}"
                )
            threat.indicator_type = ind_type

        level = data.get("threat_level")
        if level:
            if level not in THREAT_LEVELS:
                raise ValidationException(
                    f"Invalid threat_level. Must be one of: {THREAT_LEVELS}"
                )
            threat.threat_level = level

        # Parse date strings if provided
        if "first_seen" in data:
            first_seen = data.get("first_seen")
            if first_seen:
                try:
                    threat.first_seen = datetime.fromisoformat(
                        first_seen.replace("Z", "+00:00")
                    )
                except ValueError:
                    raise ValidationException(
                        "first_seen must be a valid ISO format datetime"
                    )
            else:
                threat.first_seen = None

        if "last_seen" in data:
            last_seen = data.get("last_seen")
            if last_seen:
                try:
                    threat.last_seen = datetime.fromisoformat(
                        last_seen.replace("Z", "+00:00")
                    )
                except ValueError:
                    raise ValidationException(
                        "last_seen must be a valid ISO format datetime"
                    )
            else:
                threat.last_seen = None

        if "tags" in data:
            tags = data.get("tags")
            if tags is not None and not isinstance(tags, list):
                raise ValidationException("tags must be a JSON list of strings")
            threat.tags = tags

        # Update remaining attributes
        if "indicator" in data:
            threat.indicator = data.get("indicator")
        if "source" in data:
            threat.source = data.get("source")
        if "mitre_attack" in data:
            threat.mitre_attack = data.get("mitre_attack")
        if "analyst_notes" in data:
            threat.analyst_notes = data.get("analyst_notes")
        if "assigned_analyst" in data:
            threat.assigned_analyst = data.get("assigned_analyst")

        # Track auditor
        if "last_updated_by" in data:
            threat.last_updated_by = data.get("last_updated_by")
        elif "assigned_analyst" in data:
            threat.last_updated_by = data.get("assigned_analyst")

        try:
            ThreatRepository.update(threat)
            db.session.commit()
            return threat
        except Exception as e:
            db.session.rollback()
            raise DatabaseException(f"Failed to update threat: {str(e)}")

    @staticmethod
    def update_threat_status(
        threat_id: int, new_status: str, last_updated_by: str = None
    ) -> Threat:
        """Enforces workflow state transitions and patches status."""
        threat = ThreatService.get_threat_by_id(threat_id)

        if new_status not in THREAT_STATUSES:
            raise ValidationException(
                f"Invalid status. Must be one of: {THREAT_STATUSES}"
            )

        # Check state transitions
        curr_status = threat.status
        if curr_status != new_status:
            allowed = False
            if curr_status == "Open":
                allowed = new_status in [
                    "Investigating",
                    "Contained",
                    "Closed",
                    "False Positive",
                ]
            elif curr_status == "Investigating":
                allowed = new_status in ["Contained", "Closed"]
            elif curr_status == "Contained":
                allowed = new_status == "Closed"
            elif curr_status == "False Positive":
                allowed = new_status == "Closed"
            elif curr_status == "Closed":
                allowed = False

            if not allowed:
                raise ValidationException(
                    f"State transition from '{curr_status}' to '{new_status}' is explicitly blocked by business rules."
                )

        threat.status = new_status
        if last_updated_by:
            threat.last_updated_by = last_updated_by

        try:
            db.session.commit()
            return threat
        except Exception as e:
            db.session.rollback()
            raise DatabaseException(f"Failed to patch threat status: {str(e)}")

    @staticmethod
    def delete_threat(threat_id: int) -> None:
        """Manages resource deletion lifecycle."""
        threat = ThreatService.get_threat_by_id(threat_id)
        try:
            ThreatRepository.delete(threat)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise DatabaseException(f"Failed to delete threat: {str(e)}")

    @staticmethod
    def get_stats() -> dict:
        """Calculates global threat statistics and metric tallies from database."""
        from sqlalchemy import func

        # Perform aggregate counts
        total = Threat.query.count()
        critical = Threat.query.filter(Threat.threat_level == "critical").count()
        high = Threat.query.filter(Threat.threat_level == "high").count()
        open_count = Threat.query.filter(Threat.status == "Open").count()
        closed_count = Threat.query.filter(Threat.status == "Closed").count()

        last_updated_threat = Threat.query.order_by(Threat.updated_at.desc()).first()
        last_updated = (
            last_updated_threat.updated_at.isoformat() if last_updated_threat else None
        )

        indicator_types = {
            "ip": Threat.query.filter(Threat.indicator_type == "ip").count(),
            "domain": Threat.query.filter(Threat.indicator_type == "domain").count(),
            "hash": Threat.query.filter(Threat.indicator_type == "hash").count(),
            "url": Threat.query.filter(Threat.indicator_type == "url").count(),
        }

        return {
            "total": total,
            "critical": critical,
            "high": high,
            "open": open_count,
            "closed": closed_count,
            "last_updated": last_updated,
            "indicator_types": indicator_types,
        }
