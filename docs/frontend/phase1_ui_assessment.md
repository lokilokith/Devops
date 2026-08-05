# Phase 1 UI Assessment: Frontend Architecture & Readiness

**Date:** August 2026
**Target:** Phase 1 Credential Vault UI Integration

As requested, an architectural audit of the OpsForge frontend has been conducted to verify readiness for the Credential Vault UI integration. No code has been modified.

---

## 1. Frontend Architecture Structure

The application is built on a modern, robust, and highly structured stack:

*   **Framework:** React 19 (via Vite)
*   **Routing System:** React Router v7 (`createBrowserRouter`)
*   **State Management / Data Fetching:** TanStack Query v5 (`@tanstack/react-query`) with an active cache and invalidation strategy. Local state via React Context.
*   **API Communication:** Axios interceptors handle global request headers and automatic token refreshing.
*   **Styling System:** Tailwind CSS v3 with `class-variance-authority` and `tailwind-merge` for deterministic utility merging.
*   **Component Architecture:** Feature-sliced design (`frontend/src/features/*`), paired with a generic UI component library (`frontend/src/components/ui/*`) utilizing Headless UI primitives (Radix UI) and Shadcn/ui conventions.

**Folder Structure Overview:**
```text
frontend/src/
├── api/          # Axios instances and interceptors
├── components/   # Reusable UI components (buttons, tables, modals)
├── features/     # Domain-specific modules (auth, users, roles, etc.)
├── layouts/      # Dashboard and navigational wrappers
├── routes/       # React Router configurations
├── services/     # API abstraction layers
└── utils/        # Helpers and formatting
```

---

## 2. Authentication UI & Flow

The authentication and session management layer is fully functional and secure.

*   **Login Flow:** Handled by `Login.tsx` communicating with backend `/auth/login`. Returns JWT Access and Refresh tokens.
*   **Session Handling:** `AuthContext.tsx` manages the global user state. On page load, it attempts session restoration using `/auth/me`.
*   **Token Handling:** Tokens are securely intercepted by Axios. If an access token expires, the interceptor automatically attempts to refresh it before retrying the failed request.
*   **Protected Routes:** React Router implements a `<ProtectedRoute />` wrapper that bounces unauthenticated traffic to `/login`.
*   **Authorization Guards:** The `<AuthGuard />` component evaluates granular permissions (e.g., `PERMISSIONS.USERS_READ`) and safely prevents rendering of unauthorized features.
*   **Unauthorized Handling:** Attempting to access routes without proper authorization falls back to a global `403 Unauthorized` view.

---

## 3. Existing Phase 0 UI Capabilities

The foundational administration interfaces are already implemented and functional within the `features/` directory:

*   **Dashboard:** Aggregated system status overview.
*   **User / Role / Permission Management:** Full CRUD operations mapping users to RBAC roles.
*   **Resource Management:** Abstraction mapping physical entities (like future Vaults) to policy identifiers.
*   **Access Requests & Approval Workflows:** UI exists for users to request access and for approvers to grant it.
*   **Notifications:** Real-time alert polling and visual dropdown bell.
*   **Audit Logs:** Searchable, read-only paginated view of system events.

---

## 4. Reusable Components for Vault UI

The Vault UI implementation will not require building components from scratch. The following assets are ready to be utilized:

*   **Data Table:** Reusable `TanStack Table` integration (`components/data-table/`) with pagination and sorting.
*   **Modals:** `Dialog` and `ConfirmDialog` (Radix UI) for secret creation and destructive actions (disable).
*   **Forms:** Accessible `Input`, `Textarea`, `Select`, and `Switch` components.
*   **Alerts / Toasts:** The global `Toaster` system for success/error feedback.
*   **Cards:** `Card` components for dashboard metrics or secret detail layouts.
*   **Authorization:** The `AuthGuard` wrapper can be instantly leveraged for Vault-specific permissions (e.g., `VAULT_READ`, `VAULT_WRITE`).

---

## 5. Missing Vault UI Requirements

Based on the Phase 1 backend completion, the following UI modules must be built to support the Credential Vault:

1.  **Vault Dashboard (Secret List):** 
    *   A primary view listing all `ACTIVE` secrets.
    *   Needs integration with the `data-table` component.
2.  **Secret Creation Workflow:**
    *   A modal or dedicated form to create new secrets.
    *   Requires mapping the secret to a specific `Resource`.
3.  **Secret Reveal & Interaction:**
    *   A secure mechanism to "reveal" the plaintext payload.
    *   Must handle the `403 APPROVAL_REQUIRED` response gracefully: If the policy engine demands approval, the UI should immediately prompt the user to submit an Access Request payload.
4.  **Secret Lifecycle Actions:**
    *   Dropdown actions to "Rotate" (add new version) and "Disable" (tombstone) a secret.

## Recommended Implementation Approach

The Vault UI should be constructed as a new isolated feature module (`frontend/src/features/vault/`). 
It should heavily lean on TanStack Query for caching the encrypted metadata, while actively avoiding caching the plaintext payloads in the browser state to maintain stringent security compliance.
