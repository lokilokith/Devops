"""
Integration tests for Role Management workflows.

Tests the full create → edit → activate/deactivate → delete flow,
including permission assignment/removal and duplicate validation.
"""

from __future__ import annotations

import pytest

from app.roles.exceptions import (
    DuplicateRoleError,
    RoleNotFoundError,
    ValidationError,
)
from app.roles.models import Role, RoleStatus, RoleType
from app.roles.repository import RolesRepository
from app.roles.service import RolesService


@pytest.fixture
def roles_service(db_session):
    return RolesService(RolesRepository(db_session))


# ─────────────────────────────────────────────
# CREATE ROLE
# ─────────────────────────────────────────────


class TestCreateRole:
    def test_create_role_success(self, roles_service):
        role = roles_service.create_role(
            {
                "role_code": "WF_ANALYST",
                "role_name": "Workflow Analyst",
                "description": "Can analyze workflow data",
            }
        )
        assert role.role_code == "WF_ANALYST"
        assert role.role_name == "Workflow Analyst"
        assert role.status == RoleStatus.ACTIVE
        assert role.id is not None

    def test_create_role_missing_role_code(self, roles_service):
        with pytest.raises(ValidationError):
            roles_service.create_role(
                {
                    "role_name": "No Code Role",
                }
            )

    def test_create_role_missing_role_name(self, roles_service):
        with pytest.raises(ValidationError):
            roles_service.create_role(
                {
                    "role_code": "NO_NAME",
                }
            )

    def test_create_role_duplicate_code(self, roles_service):
        roles_service.create_role(
            {
                "role_code": "WF_DUP_CODE",
                "role_name": "Duplicate Code Role 1",
            }
        )
        with pytest.raises(DuplicateRoleError) as exc:
            roles_service.create_role(
                {
                    "role_code": "WF_DUP_CODE",
                    "role_name": "Duplicate Code Role 2",
                }
            )
        assert "role code" in str(exc.value).lower()

    def test_create_role_duplicate_name(self, roles_service):
        roles_service.create_role(
            {
                "role_code": "WF_DUP_NAME_1",
                "role_name": "Shared Role Name",
            }
        )
        with pytest.raises(DuplicateRoleError) as exc:
            roles_service.create_role(
                {
                    "role_code": "WF_DUP_NAME_2",
                    "role_name": "Shared Role Name",
                }
            )
        assert "role name" in str(exc.value).lower()


# ─────────────────────────────────────────────
# READ ROLE
# ─────────────────────────────────────────────


class TestGetRole:
    def test_get_role_by_id(self, roles_service):
        created = roles_service.create_role(
            {
                "role_code": "WF_GET_ROLE",
                "role_name": "Get Role Test",
            }
        )
        fetched = roles_service.get_role(created.id)
        assert fetched.id == created.id
        assert fetched.role_code == "WF_GET_ROLE"

    def test_get_nonexistent_role(self, roles_service):
        import uuid

        with pytest.raises(RoleNotFoundError):
            roles_service.get_role(uuid.uuid4())

    def test_list_roles_returns_created(self, roles_service):
        roles_service.create_role(
            {
                "role_code": "WF_LIST_ROLE",
                "role_name": "List Role Test",
            }
        )
        roles, total = roles_service.list_roles()
        codes = [r.role_code for r in roles]
        assert "WF_LIST_ROLE" in codes
        assert total > 0


# ─────────────────────────────────────────────
# UPDATE ROLE
# ─────────────────────────────────────────────


class TestUpdateRole:
    def test_update_role_name(self, roles_service):
        role = roles_service.create_role(
            {
                "role_code": "WF_UPD_ROLE",
                "role_name": "Update Role Original",
            }
        )
        updated = roles_service.update_role(
            role.id,
            {
                "role_name": "Update Role Renamed",
            },
        )
        assert updated.role_name == "Update Role Renamed"
        # role_code should NOT change
        assert updated.role_code == "WF_UPD_ROLE"

    def test_update_role_description(self, roles_service):
        role = roles_service.create_role(
            {
                "role_code": "WF_DESC_ROLE",
                "role_name": "Description Role",
                "description": "Original description",
            }
        )
        updated = roles_service.update_role(
            role.id,
            {
                "description": "Updated description",
            },
        )
        assert updated.description == "Updated description"

    def test_update_role_status(self, roles_service):
        role = roles_service.create_role(
            {
                "role_code": "WF_STATUS_ROLE",
                "role_name": "Status Role",
            }
        )
        assert role.status == RoleStatus.ACTIVE

        updated = roles_service.update_role(
            role.id,
            {
                "status": RoleStatus.INACTIVE,
            },
        )
        assert updated.status == RoleStatus.INACTIVE

    def test_update_role_duplicate_name_raises(self, roles_service):
        roles_service.create_role(
            {
                "role_code": "WF_TAKEN_NAME",
                "role_name": "Taken Name Role",
            }
        )
        role2 = roles_service.create_role(
            {
                "role_code": "WF_OTHER_ROLE",
                "role_name": "Other Role",
            }
        )
        with pytest.raises(DuplicateRoleError):
            roles_service.update_role(role2.id, {"role_name": "Taken Name Role"})


# ─────────────────────────────────────────────
# ACTIVATE / DEACTIVATE ROLE
# ─────────────────────────────────────────────


class TestActivateDeactivateRole:
    def test_deactivate_role(self, roles_service):
        role = roles_service.create_role(
            {
                "role_code": "WF_DEACT_ROLE",
                "role_name": "Deactivate Role",
            }
        )
        assert role.status == RoleStatus.ACTIVE
        deactivated = roles_service.deactivate_role(role.id)
        assert deactivated.status == RoleStatus.INACTIVE

    def test_activate_inactive_role(self, roles_service):
        role = roles_service.create_role(
            {
                "role_code": "WF_ACT_ROLE",
                "role_name": "Activate Role",
            }
        )
        roles_service.deactivate_role(role.id)
        activated = roles_service.activate_role(role.id)
        assert activated.status == RoleStatus.ACTIVE

    def test_deactivate_nonexistent_raises(self, roles_service):
        import uuid

        with pytest.raises(Exception):  # RoleNotFoundError from repo
            roles_service.deactivate_role(uuid.uuid4())


# ─────────────────────────────────────────────
# DELETE ROLE
# ─────────────────────────────────────────────


class TestDeleteRole:
    def test_delete_custom_role_succeeds(self, roles_service):
        role = roles_service.create_role(
            {
                "role_code": "WF_DEL_ROLE",
                "role_name": "Delete Role",
            }
        )
        result = roles_service.delete_role(role.id)
        assert result is True

        # Role should be gone
        with pytest.raises(RoleNotFoundError):
            roles_service.get_role(role.id)

    def test_delete_system_role_raises(self, roles_service, db_session):
        """Cannot delete SYSTEM roles"""
        sys_role = Role(
            role_code="WF_SYS_ROLE",
            role_name="System Role No Delete",
            role_type=RoleType.SYSTEM,
        )
        db_session.add(sys_role)
        db_session.flush()
        db_session.refresh(sys_role)

        with pytest.raises(ValidationError) as exc:
            roles_service.delete_role(sys_role.id)
        assert "system" in str(exc.value).lower()

    def test_delete_nonexistent_role_raises(self, roles_service):
        import uuid

        with pytest.raises(RoleNotFoundError):
            roles_service.delete_role(uuid.uuid4())


# ─────────────────────────────────────────────
# SEARCH / LIST ROLES
# ─────────────────────────────────────────────


class TestSearchRoles:
    def test_search_by_role_code(self, roles_service):
        roles_service.create_role(
            {
                "role_code": "WF_SEARCH_CODE",
                "role_name": "Search Code Role",
            }
        )
        roles, total = roles_service.list_roles(search="WF_SEARCH_CODE")
        codes = [r.role_code for r in roles]
        assert "WF_SEARCH_CODE" in codes

    def test_search_by_role_name(self, roles_service):
        roles_service.create_role(
            {
                "role_code": "WF_SEARCH_NAME",
                "role_name": "Searchable Name Role",
            }
        )
        roles, total = roles_service.list_roles(search="Searchable Name")
        names = [r.role_name for r in roles]
        assert "Searchable Name Role" in names

    def test_count_roles(self, roles_service):
        initial_count = roles_service.count_roles()
        roles_service.create_role(
            {
                "role_code": "WF_COUNT_ROLE",
                "role_name": "Count Role",
            }
        )
        new_count = roles_service.count_roles()
        assert new_count == initial_count + 1


# ─────────────────────────────────────────────
# FULL WORKFLOW
# ─────────────────────────────────────────────


class TestFullRoleWorkflow:
    def test_complete_role_lifecycle(self, roles_service):
        """
        Full role lifecycle:
        Create → Edit → Deactivate → Activate → Delete
        """
        # 1. Create
        role = roles_service.create_role(
            {
                "role_code": "WF_FULL_LIFECYCLE",
                "role_name": "Full Lifecycle Role",
                "description": "Testing full role lifecycle",
            }
        )
        assert role.status == RoleStatus.ACTIVE

        # 2. Edit (rename and update description)
        updated = roles_service.update_role(
            role.id,
            {
                "role_name": "Full Lifecycle Role (Updated)",
                "description": "Updated description",
            },
        )
        assert updated.role_name == "Full Lifecycle Role (Updated)"

        # 3. Deactivate
        deactivated = roles_service.deactivate_role(role.id)
        assert deactivated.status == RoleStatus.INACTIVE

        # 4. Re-activate
        activated = roles_service.activate_role(role.id)
        assert activated.status == RoleStatus.ACTIVE

        # 5. Delete
        deleted = roles_service.delete_role(role.id)
        assert deleted is True

        # Verify not found after delete
        with pytest.raises(RoleNotFoundError):
            roles_service.get_role(role.id)

    def test_create_duplicate_then_delete_then_recreate(self, roles_service):
        """
        Regression: After deleting a custom role, the same role_code should be usable again.
        Roles are HARD deleted (not soft-deleted), so re-creation with same code must work.
        """
        role_data = {
            "role_code": "WF_RECREATE",
            "role_name": "Recreate Role",
        }
        # First create + delete
        role1 = roles_service.create_role(role_data)
        roles_service.delete_role(role1.id)

        # Should be able to create again
        role2 = roles_service.create_role(role_data)
        assert role2.role_code == "WF_RECREATE"
        assert role2.status == RoleStatus.ACTIVE
