from datetime import datetime, timedelta, timezone
from app.__init__ import create_app
from app.platform.extensions import db
from app.auth.models import RevokedToken
import uuid

app = create_app()
with app.app_context():
    now = datetime.now(timezone.utc)
    t1 = RevokedToken(jti=str(uuid.uuid4()), expires_at=now - timedelta(days=1))
    t2 = RevokedToken(jti=str(uuid.uuid4()), expires_at=now + timedelta(days=1))
    db.session.add(t1)
    db.session.add(t2)
    db.session.commit()
    print("Tokens inserted.")
