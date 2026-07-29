"""Script to bootstrap the RBAC tables.

Usage:
    python scripts/seed_rbac.py
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.security.bootstrap import seed_rbac
from app.security.bootstrap.rbac_seed_service import RBACSeedError

def main():
    """Run the RBAC seeder within a Flask application context."""
    app = create_app()
    with app.app_context():
        try:
            seed_rbac()
            sys.exit(0)
        except RBACSeedError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
