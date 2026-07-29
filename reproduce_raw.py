import os

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite:////l:/DOWNLOADS/Devops/opsforge/opsforge.db'
os.environ['SECRET_KEY'] = 'test-secret'

from app import create_app
from app.identity.repository import IdentityRepository
from app.platform.extensions import db

app = create_app()
with app.app_context():
    repo = IdentityRepository(db.session)
    repo.get_by_username('admin')
