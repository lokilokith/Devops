"""End-to-end test script for the Access Requests workflow."""
import sys
import os
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.platform.extensions import db
from app.identity.models import User, UserStatus
from app.roles.models import Role, RoleType
from app.access_requests.service import AccessRequestService
from app.access_requests.repository import AccessRequestRepository
from app.access_requests.models import AccessRequestStatus
from app.identity.repository import IdentityRepository
from app.roles.repository import RolesRepository
from app.resources.repository import ResourcesRepository
from app.user_roles.repository import UserRolesRepository
from dotenv import load_dotenv
load_dotenv()
from app import create_app

def run_e2e():
    app = create_app()
    with app.app_context():
        # Setup services
        service = AccessRequestService(
            AccessRequestRepository(db.session),
            IdentityRepository(db.session),
            RolesRepository(db.session),
            ResourcesRepository(db.session),
            UserRolesRepository(db.session)
        )
        
        # Get users
        requester = db.session.query(User).filter_by(username="admin").first()
        approver = requester
        
        if not requester:
            print("Admin user not found. Run seed script first.")
            sys.exit(1)
            
        # Get a role to request
        role = db.session.query(Role).first()
        if not role:
            print("No roles found.")
            sys.exit(1)
            
        print(f"User {requester.username} requesting role {role.role_name}...")
        
        # Create request
        req = service.submit_request(
            requester_id=requester.id,
            business_justification="E2E test access request",
            requested_role_id=role.id,
            requested_resource_id=None,
            priority="low"
        )
        
        print(f"Request created with ID: {req.id}, status: {req.status.name}")
        
        # Approve request
        print(f"Approving request {req.id}...")
        req = service.approve_request(req.id, approver_id=approver.id)
        
        print(f"Request approved. New status: {req.status.name}")
        
        # Verify access provisioned
        user_roles_repo = UserRolesRepository(db.session)
        has_role = False
        roles = user_roles_repo.list_roles_for_user(requester.id)
        for ur in roles:
            if ur.id == role.id:
                has_role = True
                break
                
        if has_role:
            print("Workflow SUCCESS: Role was automatically provisioned.")
        else:
            print("Workflow FAILED: Role was not provisioned.")
            
        # Cleanup
        print("Cleaning up...")
        db.session.delete(req)
        db.session.commit()

if __name__ == "__main__":
    run_e2e()
