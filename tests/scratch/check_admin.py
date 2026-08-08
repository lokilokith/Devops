import os
from sqlalchemy import select

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite:///opsforge.db'
os.environ['SECRET_KEY'] = 'test'

from app import create_app
from app.platform.extensions import db
from app.identity.models import User

app = create_app()
with app.app_context():
    admin = db.session.scalar(select(User).where(User.username == 'admin'))
    if admin:
        print("Admin user found:")
        print(f"ID: {admin.id}")
        print(f"Username: {admin.username}")
        print(f"Email: {admin.email}")
        print(f"Status: {admin.status}")
        print(f"Password hash exists: {'yes' if admin.password_hash else 'no'}")
    else:
        print("Admin user NOT found.")
