import os
from dotenv import load_dotenv
load_dotenv()
from app import create_app
app = create_app()
print('SQLALCHEMY_DATABASE_URI:', app.config.get('SQLALCHEMY_DATABASE_URI'))
print('APP_ENV:', os.environ.get('APP_ENV'))
print('CWD:', os.getcwd())
print('instance_path:', app.instance_path)

from app.platform.extensions import db
with app.app_context():
    print('db.engine.url:', db.engine.url)
