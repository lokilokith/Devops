from dotenv import load_dotenv
load_dotenv()
from app import create_app
from app.platform.extensions import db
app = create_app()
app.app_context().push()
db.create_all()
from app.cli.seed_commands import seed
app.test_cli_runner().invoke(seed)
print("Seeded successfully")
