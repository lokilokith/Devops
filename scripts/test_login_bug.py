import sys
import logging
logging.basicConfig(level=logging.DEBUG)
sys.path.insert(0, ".")

import os
os.environ["APP_ENV"] = "testing"
os.environ["JWT_SECRET_KEY"] = "super-secret"

from app import create_app
from app.extensions import db
from app.identity.models import User, UserStatus
from werkzeug.security import generate_password_hash
import uuid

app = create_app()

with app.app_context():
    db.create_all()
    db.session.query(User).delete()
    db.session.commit()
    
    u_id = uuid.uuid4()
    p_hash = generate_password_hash("secret123")
    u = User(
        id=u_id, 
        employee_id="E123", 
        username="admin", 
        email="admin@example.com", 
        full_name="Admin User", 
        password_hash=p_hash, 
        status=UserStatus.ACTIVE
    )
    db.session.add(u)
    db.session.commit()

    with app.test_client() as client:
        res = client.post(
            "/auth/login",
            json={"username": "admin", "password": "secret123"}
        )
        print("Status:", res.status_code)
        print("JSON:", res.json)
