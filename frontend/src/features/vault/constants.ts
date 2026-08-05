export const VAULT_PERMISSIONS = {
  VAULT_READ: "vault.read",
  VAULT_CREATE: "vault.create",
  VAULT_UPDATE: "vault.update",
  VAULT_DELETE: "vault.delete",
} as const;

export const SECRET_STATUS = {
  ACTIVE: "active",
  DISABLED: "disabled",
} as const;

export const VAULT_EVENTS = {
  SECRET_ACCESSED: "secret_accessed",
  SECRET_CREATED: "secret_created",
  SECRET_ROTATED: "secret_rotated",
  SECRET_DISABLED: "secret_disabled",
} as const;

export type VaultPermissionType = typeof VAULT_PERMISSIONS[keyof typeof VAULT_PERMISSIONS];
export type SecretStatusType = typeof SECRET_STATUS[keyof typeof SECRET_STATUS];
export type VaultEventType = typeof VAULT_EVENTS[keyof typeof VAULT_EVENTS];
