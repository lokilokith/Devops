import os
import traceback
from uuid import uuid4
from datetime import datetime, timezone
from app import create_app
from app.platform.extensions import db
from app.audit.models import AuditLog, AuditStatus, AuditSeverity

app = create_app()
with app.app_context():
    try:
        log = AuditLog(
            event_id=f"EVT-{uuid4().hex.upper()}",
            timestamp=datetime.now(timezone.utc),
            actor_user_id=uuid4(),
            action="test.action",
            resource_type="test",
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        db.session.add(log)
        db.session.commit()
        print("SUCCESS")
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
