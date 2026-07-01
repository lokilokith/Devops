"""WSGI Entrypoint for OpsForge.

Loads the production Flask application instance.
"""

from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()
