import os
from sqlalchemy import select

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite:///opsforge.db'
os.environ['SECRET_KEY'] = 'test'

from app import create_app
from app.platform.extensions import db
from app.permissions.models import Permission

app = create_app()
with app.app_context():
    print("--- PERMISSIONS ---")
    perms = db.session.scalars(select(Permission)).all()
    for p in perms:
        print(f"code: {p.permission_code} | name: {p.permission_name} | action: {p.action}")
