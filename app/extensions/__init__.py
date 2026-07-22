"""OpsForge Flask Extensions.

Instantiates SQLAlchemy and Migrate extensions to be initialized in create_app.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()

