import os
from flask import g
from flask_restx import Namespace, Resource
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.responses import success_response
from app.api.decorators import login_required
from app.shared.database import db

from app.access_requests.models import AccessRequest, AccessRequestStatus
from app.vault.models import VaultSecret, SecretStatus
from app.notifications.models import Notification

metrics_ns = Namespace("metrics", description="Dashboard Metrics API")

@metrics_ns.route("/dashboard")
class DashboardMetrics(Resource):
    @login_required
    def get(self):
        """Aggregate dashboard metrics."""
        
        # 1. Access Requests (Pending / Approved)
        pending_ars = db.session.query(AccessRequest).filter(AccessRequest.status == AccessRequestStatus.PENDING).count()
        approved_ars = db.session.query(AccessRequest).filter(AccessRequest.status == AccessRequestStatus.APPROVED).count()

        # 2. Active Secrets
        active_secrets = db.session.query(VaultSecret).filter(VaultSecret.status == SecretStatus.ACTIVE).count()

        # 3. Unread Notifications
        # Count unread notifications for the current user
        unread_notifs = db.session.query(Notification).filter(
            Notification.recipient_user_id == g.user_id,
            Notification.is_read == False
        ).count()

        data = {
            "access_requests": {
                "pending": pending_ars,
                "approved": approved_ars
            },
            "active_secrets": active_secrets,
            "unread_notifications": unread_notifs
        }

        return success_response(data=data, status_code=200)
