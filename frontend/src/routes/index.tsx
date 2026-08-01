import { createBrowserRouter, Navigate } from "react-router-dom"
import { DashboardLayout } from "@/layouts/DashboardLayout"
import { ProtectedRoute } from "@/features/authentication/ProtectedRoute"
import { Login } from "@/features/authentication/Login"
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
            element: <UserList />,
          },
          {
            path: "roles",
            element: <RoleList />,
          },
          {
            path: "permissions",
            element: <PermissionList />,
          },
          {
            path: "resources",
            element: <ResourceList />,
          },
          {
            path: "access-requests",
            element: <AccessRequestList />,
          },
          {
            path: "approvals",
            element: <ApprovalWorkflowList />,
          },
          {
            path: "notifications",
            element: <NotificationList />,
          },
          {
            path: "audit",
            element: <AuditLogList />,
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
