import os
import sys
from uuid import uuid4

os.environ["FLASK_APP"] = "run.py"
os.environ["APP_CONFIG_MODE"] = "testing"

from app.extensions import db
from app.audit.repository import AuditRepository
from app.audit.service import AuditService
from app.audit.models import AuditStatus, AuditSeverity, AuditLog
from app import create_app

app = create_app("testing")

with app.app_context():
    repo = AuditRepository(db.session)
    service = AuditService(repo)
    actor_id = uuid4()
    resource_id = str(uuid4())
    print("Testing log_event directly...")
    try:
        log = service.log_event(
            actor_user_id=actor_id,
            action="SECRET_CREATED",
            resource_type="vault_secrets",
            resource_id=resource_id,
            status=AuditStatus.SUCCESS,
            severity=AuditSeverity.INFO,
        )
        print(f"Log generated: {log.id}")
        count = db.session.query(AuditLog).filter_by(id=log.id).count()
        print(f"Exists in session before commit? {count}")
    except Exception as e:
        print(f"Exception during log_event: {e}")
