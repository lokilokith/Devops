"""OpsForge Threat Model.

Defines the Threat database model and its schema configuration.
"""

from datetime import datetime, timezone
from app.extensions import db
from app.constants import THREAT_LEVELS, THREAT_STATUSES, INDICATOR_TYPES


class Threat(db.Model):
    """Threat model representing a Threat Intelligence indicator."""

    __tablename__ = "threats"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    indicator = db.Column(db.String(500), nullable=False, index=True)
    indicator_type = db.Column(
        db.Enum(*INDICATOR_TYPES, name="indicator_type_enum"), nullable=False
    )
    threat_level = db.Column(
        db.Enum(*THREAT_LEVELS, name="threat_level_enum"), nullable=False, index=True
    )
    confidence = db.Column(db.Integer, nullable=False)
    mitre_attack = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(200), nullable=False)
    analyst_notes = db.Column(db.Text, nullable=True)
    assigned_analyst = db.Column(db.String(100), nullable=True)
    last_updated_by = db.Column(db.String(100), nullable=True)
    status = db.Column(
        db.Enum(*THREAT_STATUSES, name="threat_status_enum"),
        nullable=False,
        default="Open",
        index=True,
    )
    tags = db.Column(db.JSON, nullable=True)  # Uniform JSON storage

    # Timezone-aware DateTimes
    first_seen = db.Column(db.DateTime(timezone=True), nullable=True)
    last_seen = db.Column(db.DateTime(timezone=True), nullable=True)

    # Auto-populated timestamps
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        """Serializes Threat model to a dictionary representation."""

        def format_dt(dt):
            if not dt:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        return {
            "id": self.id,
            "indicator": self.indicator,
            "indicator_type": self.indicator_type,
            "threat_level": self.threat_level,
            "confidence": self.confidence,
            "mitre_attack": self.mitre_attack,
            "source": self.source,
            "analyst_notes": self.analyst_notes,
            "assigned_analyst": self.assigned_analyst,
            "last_updated_by": self.last_updated_by,
            "status": self.status,
            "tags": self.tags or [],
            "first_seen": format_dt(self.first_seen),
            "last_seen": format_dt(self.last_seen),
            "created_at": format_dt(self.created_at),
            "updated_at": format_dt(self.updated_at),
        }
