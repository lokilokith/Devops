import { createBrowserRouter, Navigate } from "react-router-dom"
import { DashboardLayout } from "@/layouts/DashboardLayout"
import { ProtectedRoute } from "@/features/authentication/ProtectedRoute"
import { Login } from "@/features/authentication/Login"
import { AuthGuard } from "@/features/authentication/AuthGuard"
import { PERMISSIONS } from "@/features/authentication/authorization"
import { Dashboard } from "@/features/dashboard/Dashboard"
import { UserList } from "@/features/users/UserList"
import { RoleList } from "@/features/roles/RoleList"
import { PermissionList } from "@/features/permissions/PermissionList"
import { ResourceList } from "@/features/resources/ResourceList"
import { AccessRequestList } from "@/features/accessRequests/AccessRequestList"
import { ApprovalWorkflowList } from "@/features/approvalWorkflow/ApprovalWorkflowList"
import { NotificationList } from "@/features/notifications/NotificationList"
import { AuditLogList } from "@/features/audit/AuditLogList"
import { Profile } from "@/features/profile/Profile"
import { Settings } from "@/features/settings/Settings"
import { NotFound } from "@/features/errors/NotFound"
import { Unauthorized } from "@/features/errors/Unauthorized"

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/",
    element: <ProtectedRoute />,
    children: [
      {
        path: "/",
        element: <DashboardLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="/dashboard" replace />,
          },
          {
            path: "dashboard",
            element: <Dashboard />,
          },
          {
            path: "users",
            element: (
              <AuthGuard requiredPermission={PERMISSIONS.USERS_READ}>
                <UserList />
              </AuthGuard>
            ),
          },
          {
            path: "roles",
            element: (
              <AuthGuard requiredPermission={PERMISSIONS.ROLES_READ}>
                <RoleList />
              </AuthGuard>
            ),
          },
          {
            path: "permissions",
            element: (
              <AuthGuard requiredPermission={PERMISSIONS.PERMISSIONS_READ}>
                <PermissionList />
              </AuthGuard>
            ),
          },
          {
            path: "resources",
            element: (
              <AuthGuard requiredPermission={PERMISSIONS.RESOURCES_READ}>
                <ResourceList />
              </AuthGuard>
            ),
          },
          {
            path: "access-requests",
            element: <AccessRequestList />, // Can be read by anyone (their own requests) or guarded by backend
          },
          {
            path: "approvals",
            element: <ApprovalWorkflowList />, // Can be read by anyone (their own approvals)
          },
          {
            path: "notifications",
            element: <NotificationList />, // Everyone has notifications
          },
          {
            path: "audit",
            element: (
              <AuthGuard requiredPermission={PERMISSIONS.AUDIT_READ}>
                <AuditLogList />
              </AuthGuard>
            ),
          },
          {
            path: "profile",
            element: <Profile />,
          },
          {
            path: "settings",
            element: <Settings />,
          },
        ],
      },
    ],
  },
  {
    path: "/403",
    element: <Unauthorized />,
  },
  {
    path: "*",
    element: <NotFound />,
  },
])
