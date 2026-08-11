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
        sqlalchemy_session_persistence = "flush"


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
    role_code = factory.Sequence(lambda n: f"RC{n:03d}")
    role_name = factory.Faker("word")
    # role_type defaults to CUSTOM, status defaults to ACTIVE
    description = factory.Faker("sentence")
    # status defaults handled by model default


from app.resources.models import Resource, ResourceType

class ResourceFactory(BaseFactory):
    class Meta:
        model = Resource

    id = factory.LazyFunction(uuid.uuid4)
    resource_code = factory.Sequence(lambda n: f"RES{n:03d}")
    resource_name = factory.Sequence(lambda n: f"Resource {n}")
    resource_type = ResourceType.SERVER
    # status defaults to active



class PermissionFactory(BaseFactory):
    class Meta:
        model = Permission

    id = factory.LazyFunction(uuid.uuid4)
    resource = factory.Sequence(lambda n: f"resource_{n}")
    action = "read"
    description = "Test Permission"




class NotificationFactory(BaseFactory):
    class Meta:
        model = Notification
        exclude = ('recipient',)

    id = factory.LazyFunction(uuid.uuid4)
    recipient = factory.SubFactory(UserFactory)
    recipient_user_id = factory.SelfAttribute('recipient.id')
    title = "Test Notification"
    message = "Message"
    type = NotificationType.SYSTEM
    status = NotificationStatus.PENDING


class AccessRequestFactory(BaseFactory):
    class Meta:
        model = AccessRequest
        exclude = ('requester', 'requested_role')

    id = factory.LazyFunction(uuid.uuid4)
    requester = factory.SubFactory(UserFactory)
    requester_id = factory.SelfAttribute('requester.id')
    status = AccessRequestStatus.PENDING
    request_number = factory.Sequence(lambda n: f"REQ-{n}")
    requested_role = factory.SubFactory(RoleFactory)
    requested_role_id = factory.SelfAttribute('requested_role.id')
    business_justification = "Testing"

class WorkflowFactory(BaseFactory):
    class Meta:
        model = ApprovalWorkflow
        exclude = ('access_request', 'approver')

    id = factory.LazyFunction(uuid.uuid4)
    access_request = factory.SubFactory(AccessRequestFactory)
    access_request_id = factory.SelfAttribute('access_request.id')
    approver = factory.SubFactory(UserFactory)
    approver_id = factory.SelfAttribute('approver.id')
    approval_level = ApprovalLevel.MANAGER
    status = ApprovalStatus.PENDING
