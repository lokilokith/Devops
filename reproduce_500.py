import os

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite:////l:/DOWNLOADS/Devops/opsforge/opsforge.db'
os.environ['SECRET_KEY'] = 'test-secret'

from app import create_app
import traceback
from app.platform.extensions import db

app = create_app()
app.config['PROPAGATE_EXCEPTIONS'] = True
client = app.test_client()

try:
    with app.app_context():
        response = client.post('/auth/login', json={'username': 'admin', 'password': 'password'})
        print(response.status_code)
        print(response.data.decode())
except Exception as e:
    traceback.print_exc()
