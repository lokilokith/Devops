import { apiClient } from "@/api/axios"

export interface Permission {
  id: string
  resource_name: string
  action: string
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
}
