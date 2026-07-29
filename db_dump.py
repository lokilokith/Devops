import os
from sqlalchemy import select

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite:///opsforge.db'
os.environ['SECRET_KEY'] = 'test'

from app import create_app
from app.platform.extensions import db
from app.identity.models import User
from app.roles.models import Role, UserRole

app = create_app()
with app.app_context():
    print("--- USERS ---")
    users = db.session.scalars(select(User)).all()
    for u in users:
        print(f"{u.id} | {u.username} | {u.employee_id}")

    print("--- ROLES ---")
    roles = db.session.scalars(select(Role)).all()
    for r in roles:
        print(f"{r.id} | {r.role_code} | {r.role_name}")

    print("--- USER_ROLES ---")
    user_roles = db.session.scalars(select(UserRole)).all()
    for ur in user_roles:
        print(f"user_id: {ur.user_id} | role_id: {ur.role_id}")
