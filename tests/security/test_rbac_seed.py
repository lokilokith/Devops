"""Tests for the RBAC Bootstrap Service."""

from sqlalchemy import select

from app.identity.models import User
from app.permissions.models import Permission
from app.resources.models import Resource
from app.role_permissions.models import RolePermission
from app.roles.models import Role, UserRole
from app.security.bootstrap.default_permissions import DEFAULT_PERMISSIONS
from app.security.bootstrap.rbac_seed_service import seed_rbac


def _create_admin_user(db_session):
    """Helper to create the required bootstrap admin user for tests."""
    admin = db_session.scalar(select(User).where(User.username == "admin"))
    if not admin:
        admin = User(
            employee_id="E-ADMIN-001",
            username="admin",
            email="admin@opsforge.internal",
            full_name="System Administrator",
        )
        db_session.add(admin)
        db_session.commit()
    return admin


def test_seed_creates_admin_user_if_missing(app, db_session):
    """Verify that the seeder creates the admin user if they are missing."""
    success = seed_rbac()
    assert success is True

    # Validate bootstrap admin user is created
    admin_user = db_session.scalar(select(User).where(User.username == "admin"))
    assert admin_user is not None

    # Validate ADMIN role exists
    admin_role = db_session.scalar(select(Role).where(Role.role_code == "ADMIN"))
    assert admin_role is not None

    # Validate ADMIN role is assigned
    ur = db_session.scalar(
        select(UserRole).where(
            UserRole.user_id == admin_user.id, UserRole.role_id == admin_role.id
        )
    )
    assert ur is not None


def test_seed_rbac_on_empty_tables(app, db_session):
    """Verify standard initialization on a fresh DB."""
    _create_admin_user(db_session)

    success = seed_rbac()
    assert success is True

    # Validate resources
    resources = db_session.scalars(select(Resource)).all()
    assert len(resources) > 0

    # Validate roles
    admin_role = db_session.scalar(select(Role).where(Role.role_code == "ADMIN"))
    assert admin_role is not None

    # Validate permissions
    permissions = db_session.scalars(select(Permission)).all()
    permission_codes = {p.permission_code for p in permissions}
    expected_codes = [f"PERM_{r.upper()}_{a.upper()}" for r, a in DEFAULT_PERMISSIONS]
    for expected_code in expected_codes:
        assert expected_code in permission_codes

    # Validate role permissions
    role_perms = db_session.scalars(
        select(RolePermission).where(RolePermission.role_id == admin_role.id)
    ).all()
    assigned_perm_ids = {rp.permission_id for rp in role_perms}
    default_perm_ids = {p.id for p in permissions if p.permission_code in expected_codes}
    assert default_perm_ids.issubset(assigned_perm_ids)

    # Validate user role
    admin_user = db_session.scalar(select(User).where(User.username == "admin"))
    ur = db_session.scalar(
        select(UserRole).where(
            UserRole.user_id == admin_user.id, UserRole.role_id == admin_role.id
        )
    )
    assert ur is not None


def test_seed_rbac_is_idempotent(app, db_session):
    """Verify that executing the seeder multiple times does not duplicate records."""
    _create_admin_user(db_session)

    # First run
    assert seed_rbac() is True

    # Capture state
    res_count = len(db_session.scalars(select(Resource)).all())
    role_count = len(db_session.scalars(select(Role)).all())
    perm_count = len(db_session.scalars(select(Permission)).all())
    ur_count = len(db_session.scalars(select(UserRole)).all())
    rp_count = len(db_session.scalars(select(RolePermission)).all())

    # Second run
    assert seed_rbac() is True

    # Verify no duplicates were created
    assert res_count == len(db_session.scalars(select(Resource)).all())
    assert role_count == len(db_session.scalars(select(Role)).all())
    assert perm_count == len(db_session.scalars(select(Permission)).all())
    assert ur_count == len(db_session.scalars(select(UserRole)).all())
    assert rp_count == len(db_session.scalars(select(RolePermission)).all())


def test_seed_rbac_partial_state(app, db_session):
    """Verify that if some resources or roles exist, it only creates the missing ones."""
    _create_admin_user(db_session)

    partial_role = db_session.scalar(select(Role).where(Role.role_code == "SOC_ANALYST"))
    if not partial_role:
        partial_role = Role(role_code="SOC_ANALYST", role_name="SOC Analyst")
        db_session.add(partial_role)

    partial_res = db_session.scalar(select(Resource).where(Resource.resource_code == "RESOURCE_USERS"))
    if not partial_res:
        partial_res = Resource(
            resource_code="RESOURCE_USERS", resource_name="User Management"
        )
        db_session.add(partial_res)
    db_session.commit()

    assert seed_rbac() is True

    # Ensure there are no duplicate SOC_ANALYST roles
    soc_roles = db_session.scalars(
        select(Role).where(Role.role_code == "SOC_ANALYST")
    ).all()
    assert len(soc_roles) == 1

    # Ensure there are no duplicate RESOURCE_USERS resources
    users_res = db_session.scalars(
        select(Resource).where(Resource.resource_code == "RESOURCE_USERS")
    ).all()
    assert len(users_res) == 1
