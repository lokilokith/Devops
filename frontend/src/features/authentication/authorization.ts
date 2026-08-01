export const ROLES = {
  ADMINISTRATOR: "Administrator",
  ADMIN: "Admin",
  USER: "User",
} as const;

export const PERMISSIONS = {
  USERS_READ: "users.read",
  USERS_CREATE: "users.create",
  USERS_UPDATE: "users.update",
  USERS_DELETE: "users.delete",
  
  ROLES_READ: "roles.read",
  ROLES_CREATE: "roles.create",
  ROLES_UPDATE: "roles.update",
  ROLES_DELETE: "roles.delete",
  
  PERMISSIONS_READ: "permissions.read",
  PERMISSIONS_CREATE: "permissions.create",
  PERMISSIONS_UPDATE: "permissions.update",
  PERMISSIONS_DELETE: "permissions.delete",
  
  RESOURCES_READ: "resources.read",
  RESOURCES_CREATE: "resources.create",
  RESOURCES_UPDATE: "resources.update",
  RESOURCES_DELETE: "resources.delete",
  
  ACCESS_REQUESTS_READ: "access_requests.read",
  ACCESS_REQUESTS_CREATE: "access_requests.create",
  ACCESS_REQUESTS_UPDATE: "access_requests.update",
  ACCESS_REQUESTS_DELETE: "access_requests.delete",
  ACCESS_REQUESTS_APPROVE: "access_requests.approve",
  ACCESS_REQUESTS_REJECT: "access_requests.reject",

  APPROVAL_WORKFLOWS_READ: "approval_workflows.read",
  APPROVAL_WORKFLOWS_CREATE: "approval_workflows.create",
  APPROVAL_WORKFLOWS_UPDATE: "approval_workflows.update",
  APPROVAL_WORKFLOWS_DELETE: "approval_workflows.delete",
  
  NOTIFICATIONS_READ: "notifications.read",
  NOTIFICATIONS_CREATE: "notifications.create",
  NOTIFICATIONS_UPDATE: "notifications.update",
  NOTIFICATIONS_DELETE: "notifications.delete",

  AUDIT_READ: "audit.read",
} as const;

export type RoleType = typeof ROLES[keyof typeof ROLES];
export type PermissionType = typeof PERMISSIONS[keyof typeof PERMISSIONS];
