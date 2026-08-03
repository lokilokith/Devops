import { apiClient } from "@/api/axios"

// Matches backend roles/schemas.py role_model
export interface Role {
  id: string
  role_code: string
  role_name: string
  role_type?: string
  description?: string
  status?: string
}

export interface RoleListParams {
  skip?: number
  limit?: number
  search?: string
}

// BUGFIX-005: role_code is REQUIRED by backend validator
export interface RoleCreatePayload {
  role_code: string
  role_name: string
  description?: string
  role_type?: string
}

export interface RoleUpdatePayload {
  role_name: string
  description?: string
  status?: string
}

export interface RolePatchPayload {
  role_name?: string
  description?: string
  status?: string
}

const unwrap = <T>(response: any): T => response.data.data

export const rolesService = {
  async listRoles(params: RoleListParams = {}): Promise<{ items: Role[]; total: number }> {
    const response = await apiClient.get("/roles", { 
      params: {
        skip: params.skip ?? 0,
        limit: params.limit ?? 10,
        search: params.search
      } 
    })
    const envelope = response.data
    return {
      items: envelope.data ?? [],
      total: envelope.meta?.total ?? (envelope.data?.length ?? 0)
    }
  },
  
  async getRole(id: string): Promise<Role> {
    const response = await apiClient.get(`/roles/${id}`)
    return unwrap<Role>(response)
  },
  
  // BUGFIX-005: createRole now requires role_code (mandatory backend field)
  async createRole(data: RoleCreatePayload): Promise<Role> {
    const response = await apiClient.post("/roles", data)
    return unwrap<Role>(response)
  },
  
  async updateRole(id: string, data: RoleUpdatePayload): Promise<Role> {
    const response = await apiClient.put(`/roles/${id}`, data)
    return unwrap<Role>(response)
  },
  
  async patchRole(id: string, data: RolePatchPayload): Promise<Role> {
    const response = await apiClient.patch(`/roles/${id}`, data)
    return unwrap<Role>(response)
  },
  
  async deleteRole(id: string): Promise<void> {
    await apiClient.delete(`/roles/${id}`)
  },

  // Permission assignment methods for role-permissions management
  async assignPermission(roleId: string, permissionId: string): Promise<{ role_id: string; permission_id: string }> {
    const response = await apiClient.post(`/roles/${roleId}/permissions`, { permission_id: permissionId })
    return unwrap(response)
  },

  async removePermission(roleId: string, permissionId: string): Promise<void> {
    await apiClient.delete(`/roles/${roleId}/permissions/${permissionId}`)
  },

  async listRolePermissions(roleId: string): Promise<any[]> {
    const response = await apiClient.get(`/roles/${roleId}/permissions`)
    return response.data.data ?? []
  },
}
