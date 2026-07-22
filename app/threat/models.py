"""OpsForge Threat Model.

Defines the SQLAlchemy structure and schema for threat intelligence records.
"""

from datetime import datetime, timezone

from app.constants import INDICATOR_TYPES, THREAT_LEVELS, THREAT_STATUSES
from app.extensions import db


class Threat(db.Model):  # type: ignore[name-defined]
    """Threat model encapsulating indicator metadata, severity, and workflow state."""

    __tablename__ = "threats"

    id = db.Column(db.Integer, primary_key=True)
    indicator = db.Column(db.String(255), nullable=False, index=True)
    indicator_type = db.Column(
        db.Enum(*INDICATOR_TYPES, name="indicator_type_enum"), nullable=False
    )
    threat_level = db.Column(
        db.Enum(*THREAT_LEVELS, name="threat_level_enum"), nullable=False, index=True
    )
    confidence = db.Column(db.Integer, nullable=False)
    mitre_attack = db.Column(db.String(50), nullable=True)
    source = db.Column(db.String(100), nullable=False)
    analyst_notes = db.Column(db.Text, nullable=True)
    assigned_analyst = db.Column(db.String(100), nullable=True)
    status = db.Column(
        db.Enum(*THREAT_STATUSES, name="threat_status_enum"),
        nullable=False,
        default="Open",
        index=True,
    )
    tags = db.Column(db.JSON, nullable=True)
    first_seen = db.Column(db.DateTime(timezone=True), nullable=True)
    last_seen = db.Column(db.DateTime(timezone=True), nullable=True)
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

    def __init__(self, **kwargs):
        """Initializes the Threat model, defaulting status to 'Open' if not provided."""
        super().__init__(**kwargs)
        if self.status is None:
            self.status = "Open"

    def to_dict(self) -> dict:
        """Serializes the Threat model instance into a dictionary."""

        def format_dt(dt: datetime) -> str | None:
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
            "status": self.status,
            "tags": self.tags or [],
            "first_seen": format_dt(self.first_seen),
            "last_seen": format_dt(self.last_seen),
            "created_at": format_dt(self.created_at),
            "updated_at": format_dt(self.updated_at),
        }

    def __repr__(self) -> str:
        """String representation of the Threat model instance."""
        return f"<Threat {self.id}: {self.indicator_type} - {self.indicator}>"

