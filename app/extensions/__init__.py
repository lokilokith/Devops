"""OpsForge Flask Extensions.

Instantiates SQLAlchemy and Migrate extensions to be initialized in create_app.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
