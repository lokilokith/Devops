"""
Integration tests for User Management workflows.

Tests the full create → edit → disable/enable → delete flow,
including regression tests for critical bugs:
- BUG-001: "second attempt fails" due to session rollback missing
- BUG-008: Archived users blocking re-registration
"""

from __future__ import annotations

import pytest
from app.identity.models import User, UserStatus
from app.identity.repository import IdentityRepository
from app.identity.service import IdentityService
from app.auth.service import AuthService
from app.identity.exceptions import (
    DuplicateUserError,
    UserNotFoundError,
    ValidationError,
)


@pytest.fixture
def user_repo(db_session):
    return IdentityRepository(db_session)


@pytest.fixture
def user_service(user_repo):
    auth_service = AuthService(user_repo)
    return IdentityService(repository=user_repo, auth_service=auth_service)


# ─────────────────────────────────────────────
# CREATE USER
# ─────────────────────────────────────────────

class TestCreateUser:
    def test_create_user_success(self, user_service):
        data = {
            "username": "wf_newuser",
            "email": "wf_newuser@test.com",
            "employee_id": "WF-001",
            "full_name": "Workflow User",
            "password": "securepassword",
        }
        user = user_service.create_user(data)
        assert user.username == "wf_newuser"
        assert user.email == "wf_newuser@test.com"
        assert user.employee_id == "WF-001"
        assert user.status == UserStatus.ACTIVE
        assert user.password_hash is not None
        assert user.id is not None

    def test_create_user_missing_required_fields(self, user_service):
        with pytest.raises(ValidationError):
            user_service.create_user({"username": "only_username"})

    def test_create_user_duplicate_username(self, user_service):
        data = {
            "username": "wf_dup_username",
            "email": "wf_dup1@test.com",
            "employee_id": "WF-DUP-01",
            "full_name": "Duplicate User 1",
            "password": "securepassword",
        }
        user_service.create_user(data)

        with pytest.raises(DuplicateUserError) as exc:
            user_service.create_user({
                **data,
                "email": "wf_dup2@test.com",
                "employee_id": "WF-DUP-02",
            })
        assert "username" in str(exc.value).lower()

    def test_create_user_duplicate_email(self, user_service):
        data = {
            "username": "wf_dup_email1",
            "email": "wf_shared@test.com",
            "employee_id": "WF-DEML-01",
            "full_name": "Email User 1",
            "password": "securepassword",
        }
        user_service.create_user(data)

        with pytest.raises(DuplicateUserError) as exc:
            user_service.create_user({
                **data,
                "username": "wf_dup_email2",
                "employee_id": "WF-DEML-02",
            })
        assert "email" in str(exc.value).lower()


# ─────────────────────────────────────────────
# READ USER
# ─────────────────────────────────────────────

class TestGetUser:
    def test_get_user_by_id(self, user_service):
        created = user_service.create_user({
            "username": "wf_getuser",
            "email": "wf_getuser@test.com",
            "employee_id": "WF-GET-01",
            "full_name": "Get User",
            "password": "securepassword",
        })
        fetched = user_service.get_user(created.id)
        assert fetched.id == created.id
        assert fetched.username == "wf_getuser"

    def test_get_nonexistent_user(self, user_service):
        import uuid
        with pytest.raises(UserNotFoundError):
            user_service.get_user(uuid.uuid4())

    def test_list_users_excludes_archived(self, user_service, user_repo):
        # Create and then archive a user
        created = user_service.create_user({
            "username": "wf_list_archived",
            "email": "wf_list_archived@test.com",
            "employee_id": "WF-LA-01",
            "full_name": "Archived User",
            "password": "securepassword",
        })
        user_repo.delete_user(created.id)  # soft-delete -> ARCHIVED

        users, total = user_service.list_users()
        usernames = [u.username for u in users]
        assert "wf_list_archived" not in usernames


# ─────────────────────────────────────────────
# UPDATE USER
# ─────────────────────────────────────────────

class TestUpdateUser:
    def test_update_user_full_name(self, user_service):
        user = user_service.create_user({
            "username": "wf_updateuser",
            "email": "wf_updateuser@test.com",
            "employee_id": "WF-UPD-01",
            "full_name": "Original Name",
            "password": "securepassword",
        })
        updated = user_service.update_user(user.id, {
            "full_name": "Updated Name",
            "status": "active",
        })
        assert updated.full_name == "Updated Name"

    def test_update_user_status_enum_coercion(self, user_service):
        """BUG-002 regression: status must be coerced to UserStatus enum"""
        user = user_service.create_user({
            "username": "wf_statuscoerce",
            "email": "wf_statuscoerce@test.com",
            "employee_id": "WF-SC-01",
            "full_name": "Status Coerce User",
            "password": "securepassword",
        })
        updated = user_service.update_user(user.id, {
            "full_name": "Status Coerce User",
            "status": "disabled",
        })
        # The status must be a proper UserStatus enum, not raw string
        assert updated.status == UserStatus.DISABLED

    def test_update_user_invalid_status_raises(self, user_service):
        """BUG-002 regression: invalid status should raise ValidationError"""
        user = user_service.create_user({
            "username": "wf_invalidstatus",
            "email": "wf_invalidstatus@test.com",
            "employee_id": "WF-IS-01",
            "full_name": "Invalid Status User",
            "password": "securepassword",
        })
        with pytest.raises(ValidationError):
            user_service.update_user(user.id, {
                "full_name": "Invalid Status User",
                "status": "not_a_real_status",
            })


# ─────────────────────────────────────────────
# ENABLE / DISABLE USER
# ─────────────────────────────────────────────

class TestEnableDisableUser:
    def test_disable_user(self, user_service):
        user = user_service.create_user({
            "username": "wf_disableuser",
            "email": "wf_disableuser@test.com",
            "employee_id": "WF-DIS-01",
            "full_name": "Disable User",
            "password": "securepassword",
        })
        assert user.status == UserStatus.ACTIVE
        disabled = user_service.deactivate_user(user.id)
        assert disabled.status == UserStatus.DISABLED

    def test_enable_user_after_disable(self, user_service):
        user = user_service.create_user({
            "username": "wf_enableuser",
            "email": "wf_enableuser@test.com",
            "employee_id": "WF-EN-01",
            "full_name": "Enable User",
            "password": "securepassword",
        })
        user_service.deactivate_user(user.id)
        enabled = user_service.activate_user(user.id)
        assert enabled.status == UserStatus.ACTIVE

    def test_disable_nonexistent_raises(self, user_service):
        import uuid
        with pytest.raises((UserNotFoundError, Exception)):
            user_service.deactivate_user(uuid.uuid4())


# ─────────────────────────────────────────────
# DELETE USER
# ─────────────────────────────────────────────

class TestDeleteUser:
    def test_delete_user_succeeds(self, user_service, user_repo):
        user = user_service.create_user({
            "username": "wf_deleteuser",
            "email": "wf_deleteuser@test.com",
            "employee_id": "WF-DEL-01",
            "full_name": "Delete User",
            "password": "securepassword",
        })
        result = user_service.delete_user(user.id)
        assert result is True

        # User should be ARCHIVED
        fetched = user_repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.status == UserStatus.ARCHIVED

    def test_delete_already_archived_returns_false(self, user_service):
        """BUG-003 regression: Second delete should return False, not True"""
        user = user_service.create_user({
            "username": "wf_deletedtwice",
            "email": "wf_deletedtwice@test.com",
            "employee_id": "WF-DEL2-01",
            "full_name": "Delete Twice User",
            "password": "securepassword",
        })
        first = user_service.delete_user(user.id)
        second = user_service.delete_user(user.id)
        assert first is True
        assert second is False  # already archived — must return False


# ─────────────────────────────────────────────
# REGRESSION: "SECOND ATTEMPT FAILS" BUG
# ─────────────────────────────────────────────

class TestSecondAttemptBugRegression:
    """
    Critical regression tests for BUG-001 and BUG-008.
    
    BUG-001: Session not rolled back after read failure → subsequent operations fail.
    BUG-008: Archived users block re-registration (exists_by_username/email includes ARCHIVED).
    """

    def test_create_delete_create_same_credentials(self, user_service):
        """
        BUG-001 + BUG-008 REGRESSION TEST:
        
        1. Create user with username A
        2. Delete (soft-delete → ARCHIVED) user  
        3. Create NEW user with same username A
        
        Expected: Step 3 succeeds. 
        Old behavior: Step 3 fails with DuplicateUserError because exists_by_username 
                      found the ARCHIVED record.
        """
        credentials = {
            "username": "wf_reregister",
            "email": "wf_reregister@test.com",
            "employee_id": "WF-REG-01",
            "full_name": "Re-Register User",
            "password": "securepassword",
        }
        # 1. Create
        user1 = user_service.create_user(credentials)
        assert user1.status == UserStatus.ACTIVE

        # 2. Delete (soft-delete)
        result = user_service.delete_user(user1.id)
        assert result is True

        # 3. Create again with same username/email — MUST SUCCEED (bug fix)
        user2 = user_service.create_user({
            **credentials,
            "employee_id": "WF-REG-02",  # different employee_id
        })
        assert user2.username == credentials["username"]
        assert user2.status == UserStatus.ACTIVE

    def test_delete_then_create_does_not_find_archived_as_duplicate(self, user_repo):
        """
        Direct repository-level regression: exists_by_username must exclude ARCHIVED users.
        """
        # Create user and archive them
        user = User(
            username="wf_repo_archived",
            email="wf_repo_archived@test.com",
            employee_id="WF-RA-01",
            full_name="Repo Archived User",
        )
        user_repo._session.add(user)
        user_repo._session.commit()

        user_repo.delete_user(user.id)  # soft-delete

        # Now check: archived username must NOT appear as duplicate
        assert user_repo.exists_by_username("wf_repo_archived") is False
        assert user_repo.exists_by_email("wf_repo_archived@test.com") is False

    def test_multiple_creates_and_deletes(self, user_service):
        """
        Stress test: create 3 users, delete all 3, then re-create all 3.
        This would fail with BUG-001/BUG-008 before fixes.
        """
        base_data = [
            {"username": "stress1", "email": "stress1@test.com", "employee_id": "ST-01"},
            {"username": "stress2", "email": "stress2@test.com", "employee_id": "ST-02"},
            {"username": "stress3", "email": "stress3@test.com", "employee_id": "ST-03"},
        ]

        # Create all
        created_ids = []
        for d in base_data:
            user = user_service.create_user({
                **d,
                "full_name": d["username"],
                "password": "securepassword",
            })
            created_ids.append(user.id)

        # Delete all
        for uid in created_ids:
            result = user_service.delete_user(uid)
            assert result is True

        # Re-create all with same credentials (new employee_id)
        for i, d in enumerate(base_data):
            new_user = user_service.create_user({
                **d,
                "employee_id": f"ST-NEW-0{i+1}",
                "full_name": d["username"],
                "password": "securepassword",
            })
            assert new_user.username == d["username"]
            assert new_user.status == UserStatus.ACTIVE


# ─────────────────────────────────────────────
# FULL WORKFLOW
# ─────────────────────────────────────────────

class TestFullUserWorkflow:
    def test_complete_lifecycle(self, user_service, user_repo):
        """
        Full user lifecycle:
        Create → Edit → Disable → Enable → Delete
        """
        # 1. Create
        user = user_service.create_user({
            "username": "wf_lifecycle",
            "email": "wf_lifecycle@test.com",
            "employee_id": "WF-LC-01",
            "full_name": "Lifecycle User",
            "password": "securepassword",
        })
        assert user.status == UserStatus.ACTIVE

        # 2. Edit
        updated = user_service.update_user(user.id, {
            "full_name": "Lifecycle User Updated",
            "status": "active",
        })
        assert updated.full_name == "Lifecycle User Updated"

        # 3. Disable
        disabled = user_service.deactivate_user(user.id)
        assert disabled.status == UserStatus.DISABLED

        # 4. Enable
        enabled = user_service.activate_user(user.id)
        assert enabled.status == UserStatus.ACTIVE

        # 5. Delete
        deleted = user_service.delete_user(user.id)
        assert deleted is True

        # Verify archived
        db_user = user_repo.get_by_id(user.id)
        assert db_user.status == UserStatus.ARCHIVED

        # Verify NOT in active listing
        users, _ = user_service.list_users()
        usernames = [u.username for u in users]
        assert "wf_lifecycle" not in usernames
