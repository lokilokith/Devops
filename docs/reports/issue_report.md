# OpsForge PAM - Root Cause Analysis Report

## BUG 1 — DARK MODE FAILURE

### Bug Description
The "Dark Mode" toggle button does not change the application's visual theme, even though the internal state reflects the selection.

### Reproduction Steps
1. Open the frontend application.
2. Click the Theme toggle button in the header.
3. Select "Dark".
4. Observe that the UI remains in light mode.

### Evidence Collected
- Checked `frontend/tailwind.config.ts`, which correctly specifies `darkMode: ["class"]`. This tells Tailwind to apply dark mode styles only when the `.dark` class is present on a parent element (typically the `<html>` tag).
- Checked `frontend/src/App.tsx`, which mounts `<ThemeProvider defaultTheme="system" storageKey="opsforge-theme">`. 
- Checked `frontend/src/components/theme-provider.tsx`, which spreads props into `next-themes`'s `NextThemesProvider`.
- Because the `attribute="class"` prop is missing from the `<ThemeProvider>` usage, `next-themes` defaults to using a data attribute (`data-theme="dark"`) instead of appending the `dark` class to the DOM. Tailwind CSS ignores this data attribute.

### Root Cause
The `next-themes` provider is not configured to output the `class` attribute required by Tailwind CSS.

### Affected Files
- `frontend/src/App.tsx`

### Proposed Fix
Update `frontend/src/App.tsx` to include the `attribute="class"` property in the `ThemeProvider`:
```tsx
<ThemeProvider defaultTheme="system" storageKey="opsforge-theme" attribute="class">
```

### Required Regression Tests
- Verify visually in the browser that clicking the Dark Theme toggle correctly applies dark colors and appends `class="dark"` to the root `<html>` element.

---

## BUG 2 — APPROVAL WORKFLOW ACTION FAILS FROM FRONTEND

### Bug Description
When an approver attempts to approve an access request from the frontend queue, the UI displays a success toast notification and the backend returns a `200 OK` HTTP status. However, the workflow status does not actually change in the database and remains "PENDING".

### Reproduction Steps
1. Navigate to the Approval Queue in the frontend.
2. Click "Approve" on a pending access request.
3. Observe the success message in the UI.
4. Refresh the page or check the backend database; the request remains "PENDING".

### Evidence Collected
- The backend route `/approval-workflows/<id>/approve` successfully processes the request and executes `svc.approve()`.
- Within `ApprovalWorkflowService.approve()`, the workflow state is updated to `APPROVED` and flushed to the database via `self._repo.update_workflow(wf)`.
- Immediately after, the service calls `self._audit.log_event()` to record the approval action.
- The `AuditRepository.create_log()` method attempts to insert the audit log and calls `self._session.commit()`. 
- However, the database is missing the `audit_logs` table because no Alembic migration was ever generated for the `app.audit.models` or `app.notifications.models`. 
- Because the table does not exist, SQLAlchemy throws an `OperationalError` / `UndefinedTable` error.
- The `AuditRepository` catches this exception, explicitly calls `self._session.rollback()`, and raises an `AuditRepositoryError`.
- `self._session.rollback()` aggressively destroys the ENTIRE database transaction, discarding the earlier `ApprovalWorkflow` state changes.
- The `AuditService` catches the `AuditRepositoryError`, logs `"Audit logging failed: Failed to create audit log."`, and silently returns `None` without propagating the exception.
- As a result, the request lifecycle continues normally, the backend responds with `200 OK`, but the database changes were completely reverted.
- We verified the missing tables by inspecting the PostgreSQL database and the `migrations/versions/` directory, confirming that neither `notifications` nor `audit_logs` migrations exist.

### Root Cause
1. **Missing Database Tables**: The `audit_logs` and `notifications` tables were never created because their models are not imported into the Alembic context, and migrations were never generated.
2. **Transaction Mismanagement in Repositories**: Side-effect repositories (`AuditRepository` and `NotificationRepository`) explicitly invoke `self._session.rollback()` upon failure. Because they share the same request-scoped session, their failure silently aborts the parent transaction (the approval update) while the parent service handles the exception as non-fatal.

### Affected Files
- `app/audit/repository.py`
- `app/notifications/repository.py`
- `migrations/versions/...` (Requires new migration)
- `app/__init__.py` (To ensure models are imported for metadata)

### Proposed Fix
1. **Generate Missing Migrations**: Import `app.audit.models` and `app.notifications.models` into the application factory and run `alembic revision --autogenerate` to create the missing tables.
2. **Implement Nested Transactions for Side Effects**: Modify `AuditRepository` and `NotificationRepository` to execute their inserts within a nested transaction (savepoint) using `with self._session.begin_nested():`. Remove explicit `self._session.commit()` and `self._session.rollback()` calls from these repository methods. This ensures that if a side-effect fails, only the savepoint is rolled back, and the primary business transaction remains intact.

### Required Regression Tests
- **API Test**: Run integration tests to ensure `/api/v1/approval-workflows/<id>/approve` actually modifies the database state and persists the `APPROVED` status.
- **Audit/Notification Test**: Verify that audit logs and notifications are successfully created in the database during an approval.
- **Savepoint Isolation Test**: Intentionally cause an audit log failure (e.g. by passing an invalid ENUM) and verify that the `ApprovalWorkflow` state still successfully commits to the database despite the audit log failure.
- **Browser Verification**: Execute the full manual approval flow in the browser and confirm the workflow disappears from the pending queue.
