import sys
sys.path.insert(0, ".")

from flask import Flask
from flask_restx import marshal
from app.roles.models import Role
from app.roles.schemas import role_model
import uuid

app = Flask(__name__)

with app.app_context():
    r = Role(id=uuid.uuid4(), role_code="ADMIN", role_name="Administrator", description="test", status="active")
    print(r)
    print(r.id)
    print(r.role_code)
    
    result = marshal([r], role_model)
    print("Marshaled:")
    print(result)
