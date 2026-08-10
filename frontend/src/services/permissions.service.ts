import { apiClient } from "@/api/axios"

export interface Permission {
  id: string
  permission_code: string
  permission_name: string
  description?: string
  action: string
  status: string
  created_at: string
  updated_at: string
}

export interface CreatePermissionRequest {
  permission_code: string
  permission_name: string
  description?: string
  action: string
}

export interface UpdatePermissionRequest {
  permission_name?: string
  description?: string
  action?: string
  status?: string
}

export interface PermissionListParams {
  skip?: number
  limit?: number
}

const unwrap = <T>(response: any): T => response.data.data

export const permissionsService = {
  async listPermissions(params: PermissionListParams = {}): Promise<{ items: Permission[]; total: number }> {
    const response = await apiClient.get("/permissions", { 
      params: {
        skip: params.skip ?? 0,
        limit: params.limit ?? 50
      } 
    })
    const envelope = response.data
    return {
      items: envelope.data ?? [],
      total: envelope.meta?.total ?? (envelope.data?.length ?? 0)
    }
  },
  
  async getPermission(id: string): Promise<Permission> {
    const response = await apiClient.get(`/permissions/${id}`)
    return unwrap<Permission>(response)
  },

  async createPermission(data: CreatePermissionRequest): Promise<Permission> {
    const response = await apiClient.post("/permissions", data)
    return unwrap<Permission>(response)
  },

  async updatePermission(id: string, data: UpdatePermissionRequest): Promise<Permission> {
    const response = await apiClient.put(`/permissions/${id}`, data)
    return unwrap<Permission>(response)
  },

  async deletePermission(id: string): Promise<void> {
    await apiClient.delete(`/permissions/${id}`)
  }
}
