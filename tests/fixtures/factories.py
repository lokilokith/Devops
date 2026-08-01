import uuid

import factory

from app.access_requests.models import AccessRequest, AccessRequestStatus
from app.approval_workflow.models import ApprovalLevel, ApprovalStatus, ApprovalWorkflow
from app.identity.models import User, UserStatus
from app.notifications.models import Notification, NotificationStatus, NotificationType
from app.permissions.models import Permission
from app.roles.models import Role
from app.shared.database import db


class BaseFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "commit"


class UserFactory(BaseFactory):
    class Meta:
        model = User

    id = factory.LazyFunction(uuid.uuid4)
    employee_id = factory.Sequence(lambda n: f"EMP{n}")
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    status = UserStatus.ACTIVE
    password_hash = "scrypt:32768:8:1$P8eGj892O1j6Q51q$775efc0702df91abfbde7dff9e24823293806fb410fdb744d2d46e30090885e3a891789c6d3df34138e6eec73c1d9f0590ed8f8c3c13ff954e7d4d422a59a764"  # hash for "secret"


class RoleFactory(BaseFactory):
    class Meta:
        model = Role

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"ROLE_{n}")
    description = "Test Role"


class PermissionFactory(BaseFactory):
    class Meta:
        model = Permission

    id = factory.LazyFunction(uuid.uuid4)
    resource = factory.Sequence(lambda n: f"resource_{n}")
    action = "read"
    description = "Test Permission"


class WorkflowFactory(BaseFactory):
    class Meta:
        model = ApprovalWorkflow

    id = factory.LazyFunction(uuid.uuid4)
    access_request_id = factory.LazyFunction(uuid.uuid4)
    approver_id = factory.LazyFunction(uuid.uuid4)
    approval_level = ApprovalLevel.MANAGER
    status = ApprovalStatus.PENDING


class NotificationFactory(BaseFactory):
    class Meta:
        model = Notification

    id = factory.LazyFunction(uuid.uuid4)
    recipient_user_id = factory.LazyFunction(
        lambda: str(uuid.uuid4())
    )  # Must be overridden
    title = "Test Notification"
    message = "Message"
    type = NotificationType.SYSTEM
    status = NotificationStatus.PENDING


class AccessRequestFactory(BaseFactory):
    class Meta:
        model = AccessRequest

    id = factory.LazyFunction(uuid.uuid4)
    requester_id = factory.LazyFunction(uuid.uuid4)
    status = AccessRequestStatus.PENDING
    request_number = factory.Sequence(lambda n: f"REQ-{n}")
    requested_role_id = factory.LazyFunction(uuid.uuid4)
    business_justification = "Testing"
