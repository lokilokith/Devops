import os
os.environ["APP_ENV"] = "testing"
from app import create_app
from app.extensions import db
from app.identity.models import User, UserStatus
import uuid
from werkzeug.security import generate_password_hash

app = create_app()
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://opsforge_test:opsforge_test@localhost:5440/opsforge_test"

with app.app_context():
    db.create_all()
    user = User(
        id=uuid.uuid4(),
        employee_id="test_enum1",
        username="test_enum1",
        email="test_enum1@example.com",
        full_name="Test Enum",
        password_hash=generate_password_hash("test"),
        status=UserStatus.ACTIVE
    )
    db.session.add(user)
    db.session.commit()
    
    # Reload user
    u = db.session.query(User).filter_by(username="test_enum1").first()
    print(f"Type of user.status from PostgreSQL: {type(u.status)}")
    if isinstance(u.status, str):
        print("It is a STRING!")
    else:
        print("It is an ENUM!")
        print(f"Value: {u.status.value}")
