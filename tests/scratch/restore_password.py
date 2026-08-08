import os
from sqlalchemy import select

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite:///opsforge.db'
os.environ['SECRET_KEY'] = 'test'

from app import create_app
from app.platform.extensions import db
from app.identity.models import User
from app.auth.service import AuthService
from app.identity.repository import IdentityRepository

app = create_app()
with app.app_context():
    admin = db.session.scalar(select(User).where(User.username == 'admin'))
    if admin:
        service = AuthService(IdentityRepository(db.session))
        admin.password_hash = service.hash_password("secret123")
        db.session.commit()
        print("Password restored to secret123")
