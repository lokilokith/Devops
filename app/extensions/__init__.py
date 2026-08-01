"""OpsForge Flask Extensions.

Instantiates SQLAlchemy and Migrate extensions to be initialized in create_app.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address)

