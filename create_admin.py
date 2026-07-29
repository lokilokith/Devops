from app.platform.extensions import db
from app.identity.models import User, UserStatus
from app import create_app

app = create_app("development")
with app.app_context():
    u = User(employee_id="ADMIN_SEED", username="admin", email="admin@opsforge.internal", full_name="System Admin", status=UserStatus.ACTIVE)
    from app.identity.service import IdentityService
    from app.identity.repository import IdentityRepository
    svc = IdentityService(IdentityRepository(db.session))
    svc.create_user("admin", "admin@opsforge.internal", "secret123", "ADMIN_SEED", "System Admin")
    print("Admin user created.")
