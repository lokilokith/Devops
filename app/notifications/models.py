from enum import Enum

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON, Uuid

from app.platform.extensions import db
from app.shared.database import BaseModel


class NotificationType(str, Enum):
    ACCESS_REQUEST_CREATED = "access_request_created"
    APPROVAL_REQUIRED = "approval_required"
    REQUEST_APPROVED = "request_approved"
    REQUEST_REJECTED = "request_rejected"
    REQUEST_CANCELLED = "request_cancelled"
    ROLE_PROVISIONED = "role_provisioned"
    SYSTEM = "system"
    AUDIT_ALERT = "audit_alert"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Notification(BaseModel):
    __tablename__ = "notifications"

    recipient_user_id = db.Column(
        Uuid(as_uuid=True), db.ForeignKey("users.id"), nullable=False, index=True
    )
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)

    type = db.Column(
        db.Enum(NotificationType, name="notification_type"), nullable=False
    )
    status = db.Column(
        db.Enum(NotificationStatus, name="notification_status"),
        nullable=False,
        default=NotificationStatus.PENDING,
    )
    priority = db.Column(
        db.Enum(NotificationPriority, name="notification_priority"),
        nullable=False,
        default=NotificationPriority.NORMAL,
    )

    is_read = db.Column(db.Boolean, nullable=False, default=False)
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)

    delivery_attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)

    metadata_payload = db.Column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    recipient = db.relationship("User", backref="notifications", lazy=True)
