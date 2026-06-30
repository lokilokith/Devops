"""OpsForge Flask Extensions.

Instantiates database and migration extensions to be registered by the application factory.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
