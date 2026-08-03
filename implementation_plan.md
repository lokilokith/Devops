# OpsForge PAM Phase 2 Implementation Plan

## Goal Description
Implement the fixes for Bug 1 (Dark Mode Failure) and Bug 2 (Approval Workflow Silent Failure) based on the approved root cause analysis. Ensure atomic transactions across the approval workflow and generate the missing database migrations.

## User Review Required
> [!IMPORTANT]
> The transaction handling changes will alter the behavior of `AuditService` and `NotificationService`. Previously they swallowed exceptions silently. Now they will raise exceptions and abort the parent transaction if audit logging or notifications fail. This enforces strict atomicity but means that a failure in the notification system will block access request approvals. Is this strict atomicity desired for notifications as well, or should notifications be asynchronous/non-blocking while audit logs remain strictly blocking?
> Based on your request ("If ANY step fails: ROLLBACK. Return error response"), I will implement strictly blocking atomicity for both.

## Proposed Changes

---

### Frontend

#### [MODIFY] [App.tsx](file:///l:/DOWNLOADS/Devops/opsforge/frontend/src/App.tsx)
- Update the `<ThemeProvider>` component to include `attribute="class"` so that `next-themes` toggles the `class="dark"` attribute on the HTML root element as expected by Tailwind CSS.

---

### Backend Database Migrations

#### [NEW] `migrations/versions/xxxx_add_audit_and_notifications.py`
- Expose `app.audit.models` and `app.notifications.models` to the Alembic environment (e.g. by importing them in `app/__init__.py` alongside other models).
- Run `flask db migrate -m "Add audit and notifications tables"` to generate the missing tables.

---

### Backend Transaction Handling

#### [MODIFY] [app/audit/repository.py](file:///l:/DOWNLOADS/Devops/opsforge/app/audit/repository.py)
- Remove explicit `self._session.commit()` and `self._session.rollback()` calls from `create_log`.
- Replace `commit()` with `self._session.flush()` to ensure changes are staged within the current active transaction but not fully committed until the service layer (or route) completes successfully.

#### [MODIFY] [app/notifications/repository.py](file:///l:/DOWNLOADS/Devops/opsforge/app/notifications/repository.py)
- Remove explicit `self._session.rollback()` calls from `create_notification`, `update_notification`, and `delete_notification`.
- Allow SQLAlchemy exceptions to bubble up as `NotificationRepositoryError` while leaving the transaction marked for rollback.

#### [MODIFY] [app/audit/service.py](file:///l:/DOWNLOADS/Devops/opsforge/app/audit/service.py)
- Remove silent exception swallowing in `log_event()`. Instead of returning `None` on failure, it will now re-raise the exception, causing the parent business transaction to abort.

#### [MODIFY] [app/notifications/service.py](file:///l:/DOWNLOADS/Devops/opsforge/app/notifications/service.py)
- Ensure exceptions during notification creation bubble up to abort the transaction.

#### [MODIFY] [app/approval_workflow/service.py](file:///l:/DOWNLOADS/Devops/opsforge/app/approval_workflow/service.py)
- Ensure the `approve` method does not catch and silently suppress these new exceptions. The errors should propagate to the REST API, resulting in an HTTP 500 (or appropriate 4xx) response, guaranteeing "Never return success" on failure.

---

### Testing

#### [NEW] [tests/integration/test_approval_workflow_atomicity.py](file:///l:/DOWNLOADS/Devops/opsforge/tests/integration/test_approval_workflow_atomicity.py)
- Test: Successful approval creates workflow, user roles, audit logs, and notifications.
- Test: Failed audit logging rolls back the entire transaction.
- Test: Failed notification creation rolls back the entire transaction.
- Test: Duplicate approval attempt fails and returns conflict.

## Verification Plan
### Automated Tests
- `pytest tests/`
- `pytest --cov=app --cov-fail-under=85`

### Manual Verification
- Rebuild docker containers: `docker compose build --no-cache && docker compose up -d`
- Browser test: End-to-end creation and approval of an access request.
- Browser test: Verify dark mode toggle visually updates the UI and persists on refresh.
- Check database explicitly (`docker exec ... psql`) to ensure all tables exist and are populated.
